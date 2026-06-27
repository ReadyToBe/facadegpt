from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from database import get_connection
from .llm_client import OpenAIUnavailable, embed_texts, has_openai_key
from .settings import BOOKS_DIR

CHUNK_TARGET_CHARS = 1800
CHUNK_OVERLAP_CHARS = 220


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return words


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Missing dependency pypdf. Run: pip install -r backend/requirements.txt") from exc
    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text.strip():
            pages.append((index, text.strip()))
    return pages


def _chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    chunks: list[dict] = []
    buffer = ""
    page_start = None
    page_end = None
    for page_number, text in pages:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        for paragraph in paragraphs:
            if not buffer:
                page_start = page_number
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) >= CHUNK_TARGET_CHARS and buffer:
                chunks.append({"page_start": page_start, "page_end": page_end or page_number, "text": buffer})
                buffer = buffer[-CHUNK_OVERLAP_CHARS:] + "\n\n" + paragraph
                page_start = page_number
            else:
                buffer = candidate
            page_end = page_number
    if buffer.strip():
        chunks.append({"page_start": page_start or 1, "page_end": page_end or page_start or 1, "text": buffer.strip()})
    return chunks


def _embed_chunks(chunks: list[dict], use_api_embeddings: bool) -> None:
    if not use_api_embeddings or not has_openai_key():
        return
    batch_size = 24
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embed_texts([chunk["text"][:8000] for chunk in batch])
        for chunk, embedding in zip(batch, embeddings):
            chunk["embedding"] = embedding


def rebuild_knowledge_base(use_api_embeddings: bool = True) -> dict:
    BOOKS_DIR.mkdir(exist_ok=True)
    pdfs = sorted(BOOKS_DIR.glob("*.pdf"))
    results = []
    with get_connection() as conn:
        for pdf in pdfs:
            doc_id = str(uuid.uuid4())
            title = pdf.stem
            now = _now()
            conn.execute("DELETE FROM knowledge_documents WHERE source_path = ?", (str(pdf),))
            conn.execute(
                """
                INSERT INTO knowledge_documents
                (id, source_path, title, status, created_at, updated_at)
                VALUES (?, ?, ?, 'processing', ?, ?)
                """,
                (doc_id, str(pdf), title, now, now),
            )
            try:
                pages = _extract_pdf_pages(pdf)
                chunks = _chunk_pages(pages)
                try:
                    _embed_chunks(chunks, use_api_embeddings)
                    embedding_status = "embedded" if chunks and chunks[0].get("embedding") else "keyword-only"
                except OpenAIUnavailable as exc:
                    embedding_status = f"keyword-only: {exc}"
                for index, chunk in enumerate(chunks):
                    conn.execute(
                        """
                        INSERT INTO knowledge_chunks
                        (id, document_id, chunk_index, page_start, page_end, text, embedding)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            doc_id,
                            index,
                            chunk["page_start"],
                            chunk["page_end"],
                            chunk["text"],
                            json.dumps(chunk.get("embedding")) if chunk.get("embedding") else None,
                        ),
                    )
                conn.execute(
                    """
                    UPDATE knowledge_documents
                    SET status='ready', page_count=?, chunk_count=?, error=?, updated_at=?
                    WHERE id=?
                    """,
                    (len(pages), len(chunks), embedding_status, _now(), doc_id),
                )
                results.append({"title": title, "pages": len(pages), "chunks": len(chunks), "status": "ready", "mode": embedding_status})
            except Exception as exc:
                conn.execute(
                    "UPDATE knowledge_documents SET status='error', error=?, updated_at=? WHERE id=?",
                    (str(exc), _now(), doc_id),
                )
                results.append({"title": title, "status": "error", "error": str(exc)})
    return {"documents": results, "document_count": len(results)}


def knowledge_status() -> dict:
    with get_connection() as conn:
        documents = conn.execute(
            """
            SELECT id, title, source_path, status, page_count, chunk_count, error, updated_at
            FROM knowledge_documents ORDER BY updated_at DESC
            """
        ).fetchall()
        chunk_count = conn.execute("SELECT COUNT(*) AS count FROM knowledge_chunks").fetchone()["count"]
    return {"documents": [dict(row) for row in documents], "chunk_count": chunk_count}


def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.text, c.page_start, c.page_end, c.embedding,
                   d.title, d.source_path
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE d.status = 'ready'
            """
        ).fetchall()
    if not rows:
        return []

    query_embedding = None
    if has_openai_key() and any(row["embedding"] for row in rows):
        try:
            query_embedding = embed_texts([query])[0]
        except OpenAIUnavailable:
            query_embedding = None

    scored = []
    query_terms = Counter(_tokenize(query))
    for row in rows:
        score = 0.0
        if query_embedding and row["embedding"]:
            score = _cosine(query_embedding, json.loads(row["embedding"]))
        else:
            terms = Counter(_tokenize(row["text"]))
            if query_terms:
                score = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
                score = score / max(1, math.sqrt(sum(terms.values())))
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": round(score, 4),
            "title": row["title"],
            "source_path": row["source_path"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "text": row["text"],
        }
        for score, row in scored[:limit]
    ]


def format_context(results: list[dict], max_chars: int = 6500) -> str:
    parts: list[str] = []
    total = 0
    for index, item in enumerate(results, start=1):
        citation = f"[{index}] {item['title']}, pp. {item['page_start']}-{item['page_end']}"
        text = item["text"].strip()
        part = f"{citation}\n{text}"
        if total + len(part) > max_chars:
            part = part[: max(0, max_chars - total)]
        if part:
            parts.append(part)
            total += len(part)
        if total >= max_chars:
            break
    return "\n\n---\n\n".join(parts)

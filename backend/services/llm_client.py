from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from .settings import (
    deepseek_api_key,
    deepseek_base_url,
    deepseek_model,
    embedding_model,
    llm_provider,
    openai_api_key,
    openai_model,
)

OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAIUnavailable(RuntimeError):
    pass


def has_openai_key() -> bool:
    if llm_provider() == "deepseek":
        return bool(deepseek_api_key())
    return bool(openai_api_key())


def provider_status() -> dict:
    provider = llm_provider()
    if provider == "deepseek":
        return {
            "provider": "deepseek",
            "configured": bool(deepseek_api_key()),
            "model": deepseek_model(),
            "base_url": deepseek_base_url(),
            "embedding_provider": "keyword-only unless OPENAI_API_KEY is also set",
            "embedding_configured": bool(openai_api_key()),
            "embedding_model": embedding_model(),
        }
    return {
        "provider": "openai",
        "configured": bool(openai_api_key()),
        "model": openai_model(),
        "embedding_provider": "openai",
        "embedding_configured": bool(openai_api_key()),
        "embedding_model": embedding_model(),
    }


def _post_json(url: str, payload: dict, api_key: str, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIUnavailable(f"LLM API error {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise OpenAIUnavailable(f"LLM API request failed: {exc}") from exc


def _deepseek_chat(messages: list[dict], json_mode: bool = False) -> str:
    key = deepseek_api_key()
    if not key:
        raise OpenAIUnavailable("DEEPSEEK_API_KEY is not configured")
    payload: dict = {
        "model": deepseek_model(),
        "messages": messages,
        "stream": False,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post_json(f"{deepseek_base_url()}/chat/completions", payload, key)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIUnavailable("DeepSeek response did not contain message content") from exc


def _openai_responses(messages: list[dict]) -> str:
    key = openai_api_key()
    if not key:
        raise OpenAIUnavailable("OPENAI_API_KEY is not configured")
    data = _post_json(
        f"{OPENAI_API_BASE}/responses",
        {"model": openai_model(), "input": messages},
        key,
    )
    return extract_output_text(data).strip()


def generate_json(system_prompt: str, user_prompt: str, schema_hint: str) -> dict:
    messages = [
        {"role": "system", "content": f"{system_prompt}\nYou must output valid JSON."},
        {"role": "user", "content": f"{user_prompt}\n\nReturn strict JSON only. Schema:\n{schema_hint}"},
    ]
    if llm_provider() == "deepseek":
        text = _deepseek_chat(messages, json_mode=True)
    else:
        text = _openai_responses(messages)
    return _loads_json_object(text)


def generate_text(system_prompt: str, user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if llm_provider() == "deepseek":
        return _deepseek_chat(messages, json_mode=False)
    return _openai_responses(messages)


def generate_chat(system_prompt: str, messages: list[dict]) -> str:
    chat_messages = [{"role": "system", "content": system_prompt}]
    chat_messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in messages
        if item.get("role") in {"user", "assistant"} and item.get("content")
    )
    if llm_provider() == "deepseek":
        return _deepseek_chat(chat_messages, json_mode=False)
    return _openai_responses(chat_messages)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    key = openai_api_key()
    if not key:
        raise OpenAIUnavailable("Embeddings require OPENAI_API_KEY; DeepSeek provider does not expose embeddings here")
    data = _post_json(
        f"{OPENAI_API_BASE}/embeddings",
        {"model": embedding_model(), "input": texts},
        key,
    )
    return [item["embedding"] for item in data.get("data", [])]


def extract_output_text(response: dict) -> str:
    if "output_text" in response:
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and "text" in content:
                chunks.append(content["text"])
    if not chunks:
        raise OpenAIUnavailable("Response did not contain text output")
    return "".join(chunks)


def _loads_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise

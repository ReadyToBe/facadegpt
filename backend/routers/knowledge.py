from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from services.knowledge_base import knowledge_status, rebuild_knowledge_base, search_knowledge
from services.image_client import image_provider_status
from services.llm_client import provider_status

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class RebuildRequest(BaseModel):
    use_api_embeddings: bool = True


@router.get("/status")
def status():
    data = knowledge_status()
    data["llm"] = provider_status()
    data["image"] = image_provider_status()
    data["openai"] = {
        "configured": data["llm"]["configured"],
        "model": data["llm"]["model"],
        "provider": data["llm"]["provider"],
    }
    return data


@router.post("/rebuild")
def rebuild(payload: RebuildRequest):
    return rebuild_knowledge_base(use_api_embeddings=payload.use_api_embeddings)


@router.get("/search")
def search(q: str, limit: int = 5):
    return {"results": search_knowledge(q, limit)}

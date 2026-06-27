from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import init_db
from services.knowledge_base import rebuild_knowledge_base


if __name__ == "__main__":
    init_db()
    result = rebuild_knowledge_base(use_api_embeddings=True)
    print(result)

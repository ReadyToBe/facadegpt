from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from fastapi import Header, HTTPException

DEFAULT_LOCAL_USER_ID = "local-anonymous-user"
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{3,128}$")


def current_user_id(
    x_facadegpt_user_id: Annotated[str | None, Header(alias="X-FacadeGPT-User-Id")] = None,
) -> str:
    user_id = (x_facadegpt_user_id or DEFAULT_LOCAL_USER_ID).strip()
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(400, "Invalid FacadeGPT user id")
    return user_id


def ensure_user(conn, user_id: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO users (id, seed_project_created, created_at, last_seen_at)
        VALUES (?, 0, ?, ?)
        ON CONFLICT(id) DO UPDATE SET last_seen_at = excluded.last_seen_at
        """,
        (user_id, now, now),
    )

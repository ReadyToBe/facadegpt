from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import current_user_id, ensure_user
from database import get_connection, row_to_dict
from services.demand_parser import PARAMETER_DEFAULTS, parse_demand
from services.ga_optimizer import STRATEGIES, optimize
from services.project_chat import respond_to_project_chat
from services.project_welcome import PROJECT_WELCOME_MESSAGE
from services.teaching_feedback import build_feedback

router = APIRouter(prefix="/api/projects", tags=["projects"])
UserId = Annotated[str, Depends(current_user_id)]
EXAMPLE_PROJECT_NAME = "FacadeGPT 示例项目"


class ProjectCreate(BaseModel):
    name: str


class DemandRequest(BaseModel):
    natural_language: str


class ChatRequest(BaseModel):
    message: str


class WeightsRequest(BaseModel):
    weight_lcce: float
    weight_lcc: float
    weight_sda: float
    source: str | None = None


class GenerateRequest(BaseModel):
    num_schemes: int = 3
    strategies: list[str] = ["balanced", "low-carbon", "low-cost"]


def _insert_ranges(conn, project_id: str, ranges: list[dict]) -> None:
    conn.execute("DELETE FROM parameter_ranges WHERE project_id = ?", (project_id,))
    for item in ranges:
        conn.execute(
            """
            INSERT INTO parameter_ranges
            (id, project_id, param_name, param_type, min_val, max_val, options, fixed_val, unit, step, is_locked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                item["param_name"],
                item["param_type"],
                item.get("min_val"),
                item.get("max_val"),
                json.dumps(item.get("options"), ensure_ascii=False) if item.get("options") else None,
                item.get("fixed_val"),
                item.get("unit"),
                item.get("step"),
                1 if item.get("is_locked") else 0,
            ),
        )


def _create_project_record(conn, user_id: str, name: str) -> dict:
    project_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    welcome_message_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, user_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, user_id, name, now, now),
    )
    conn.execute("INSERT INTO project_info (project_id) VALUES (?)", (project_id,))
    _insert_ranges(conn, project_id, PARAMETER_DEFAULTS)
    conn.execute(
        "INSERT INTO project_messages (id, project_id, role, content, created_at) VALUES (?, ?, 'assistant', ?, ?)",
        (welcome_message_id, project_id, PROJECT_WELCOME_MESSAGE, now),
    )
    return {"project_id": project_id, "name": name, "created_at": now}


def _ensure_user_workspace(conn, user_id: str) -> None:
    ensure_user(conn, user_id)
    has_project = conn.execute("SELECT id FROM projects WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    if has_project:
        return

    legacy_count = conn.execute("SELECT COUNT(*) AS count FROM projects WHERE user_id IS NULL").fetchone()["count"]
    if legacy_count:
        conn.execute("UPDATE projects SET user_id = ? WHERE user_id IS NULL", (user_id,))
        conn.execute("UPDATE users SET seed_project_created = 1 WHERE id = ?", (user_id,))
        return

    user = conn.execute("SELECT seed_project_created FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user["seed_project_created"]:
        return

    _create_project_record(conn, user_id, EXAMPLE_PROJECT_NAME)
    conn.execute("UPDATE users SET seed_project_created = 1 WHERE id = ?", (user_id,))


def _require_project(conn, project_id: str, user_id: str, columns: str = "id"):
    project = conn.execute(
        f"SELECT {columns} FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, user_id: UserId):
    with get_connection() as conn:
        ensure_user(conn, user_id)
        project = _create_project_record(conn, user_id, payload.name)
    return project


@router.get("")
def list_projects(user_id: UserId):
    with get_connection() as conn:
        _ensure_user_workspace(conn, user_id)
        rows = conn.execute(
            """
            SELECT p.id AS project_id, p.name, p.created_at, COUNT(s.id) AS scheme_count
            FROM projects p LEFT JOIN schemes s ON s.project_id = p.id
            WHERE p.user_id = ?
            GROUP BY p.id ORDER BY p.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return {"projects": [dict(row) for row in rows]}


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user_id: UserId):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Project not found")
    return Response(status_code=204)


@router.get("/{project_id}")
def get_project(project_id: str, user_id: UserId):
    with get_connection() as conn:
        project = _require_project(conn, project_id, user_id, "id AS project_id, name, created_at")
        info = conn.execute("SELECT * FROM project_info WHERE project_id = ?", (project_id,)).fetchone()
        ranges = conn.execute("SELECT * FROM parameter_ranges WHERE project_id = ?", (project_id,)).fetchall()
    return {"project": dict(project), "project_info": row_to_dict(info), "parameter_ranges": [row_to_dict(row) for row in ranges]}


@router.get("/{project_id}/messages")
def list_project_messages(project_id: str, user_id: UserId):
    with get_connection() as conn:
        _require_project(conn, project_id, user_id)
        rows = conn.execute(
            """
            SELECT id AS message_id, role, content,
                   replace(created_at, ' ', 'T') || 'Z' AS created_at
            FROM project_messages
            WHERE project_id = ?
            ORDER BY created_at, rowid
            """,
            (project_id,),
        ).fetchall()
    return {"project_id": project_id, "messages": [dict(row) for row in rows]}


@router.post("/{project_id}/chat")
def chat_with_project(project_id: str, payload: ChatRequest, user_id: UserId):
    message = payload.message.strip()
    if not message:
        raise HTTPException(400, "消息不能为空")
    now = datetime.now().isoformat(timespec="seconds")
    user_message = {"message_id": str(uuid.uuid4()), "role": "user", "content": message, "created_at": now}
    with get_connection() as conn:
        project = _require_project(conn, project_id, user_id, "id, name")
        info = conn.execute("SELECT * FROM project_info WHERE project_id = ?", (project_id,)).fetchone()
        if not info:
            raise HTTPException(404, "Project not found")
        conn.execute(
            "INSERT INTO project_messages (id, project_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
            (user_message["message_id"], project_id, message, now),
        )
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in conn.execute(
                "SELECT role, content FROM project_messages WHERE project_id = ? ORDER BY created_at, rowid",
                (project_id,),
            ).fetchall()
        ]

    reply = respond_to_project_chat(dict(project), dict(info), history)
    assistant_message = {
        "message_id": str(uuid.uuid4()),
        "role": "assistant",
        "content": reply,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_messages (id, project_id, role, content, created_at) VALUES (?, ?, 'assistant', ?, ?)",
            (assistant_message["message_id"], project_id, reply, assistant_message["created_at"]),
        )
        conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ? AND user_id = ?",
            (assistant_message["created_at"], project_id, user_id),
        )
    return {"user_message": user_message, "assistant_message": assistant_message}


@router.get("/{project_id}/schemes")
def list_project_schemes(project_id: str, user_id: UserId):
    with get_connection() as conn:
        _require_project(conn, project_id, user_id)
        rows = conn.execute(
            """
            SELECT id AS scheme_id, scheme_name, scheme_label, strategy,
                   replace(created_at, ' ', 'T') || 'Z' AS created_at,
                   description, risk_note, fitness_score
            FROM schemes
            WHERE project_id = ?
            ORDER BY created_at DESC, rowid DESC
            """,
            (project_id,),
        ).fetchall()
        schemes = []
        for row in rows:
            scheme = dict(row)
            params = conn.execute(
                "SELECT * FROM scheme_params WHERE scheme_id = ?", (scheme["scheme_id"],)
            ).fetchone()
            performance = conn.execute(
                "SELECT * FROM scheme_performance WHERE scheme_id = ?", (scheme["scheme_id"],)
            ).fetchone()
            scheme["params"] = dict(params) if params else {}
            scheme["performance"] = dict(performance) if performance else {}
            schemes.append(scheme)
    return {"project_id": project_id, "schemes": schemes}


@router.post("/{project_id}/parse-demand")
def parse_project_demand(project_id: str, payload: DemandRequest, user_id: UserId):
    parsed = parse_demand(payload.natural_language)
    info = parsed["project_info"]
    weights = info["weights"]
    with get_connection() as conn:
        _require_project(conn, project_id, user_id)
        conn.execute(
            """
            UPDATE project_info SET location=?, climate_zone=?, building_type=?, orientation=?,
            weight_lcce=?, weight_lcc=?, weight_sda=?, demand_text=? WHERE project_id=?
            """,
            (info["location"], info["climate_zone"], info["building_type"], info["orientation"], weights["lcce"], weights["lcc"], weights["sda"], payload.natural_language, project_id),
        )
        _insert_ranges(conn, project_id, parsed["parameter_ranges"])
    return parsed


@router.put("/{project_id}/weights")
def update_weights(project_id: str, payload: WeightsRequest, user_id: UserId):
    total = round(payload.weight_lcce + payload.weight_lcc + payload.weight_sda, 4)
    if total != 1:
        raise HTTPException(400, "三项目标权重之和必须等于 1")
    with get_connection() as conn:
        _require_project(conn, project_id, user_id)
        conn.execute(
            "UPDATE project_info SET weight_lcce=?, weight_lcc=?, weight_sda=?, weight_preset='custom' WHERE project_id=?",
            (payload.weight_lcce, payload.weight_lcc, payload.weight_sda, project_id),
        )
    return {"project_id": project_id, "updated_weights": {"lcce": payload.weight_lcce, "lcc": payload.weight_lcc, "sda": payload.weight_sda}, "message": "权重已更新，点击'重新生成'以应用新权重"}


STRATEGY_NAMES = {
    "balanced": "综合平衡",
    "low-carbon": "低碳优先",
    "low-cost": "成本优先",
    "custom": "自定义权重",
}


@router.post("/{project_id}/generate-schemes")
def generate_schemes(project_id: str, payload: GenerateRequest, user_id: UserId):
    # Step 1: read project data (keep the DB transaction short).
    with get_connection() as conn:
        project = _require_project(conn, project_id, user_id, "name")
        info = conn.execute("SELECT * FROM project_info WHERE project_id = ?", (project_id,)).fetchone()
        ranges = [row_to_dict(row) for row in conn.execute("SELECT * FROM parameter_ranges WHERE project_id = ?", (project_id,)).fetchall()]
        existing_count = conn.execute("SELECT COUNT(*) AS count FROM schemes WHERE project_id = ?", (project_id,)).fetchone()["count"]
    if not info:
        raise HTTPException(404, "Project not found")

    # Step 2: compute all schemes and teaching feedback outside the DB transaction.
    # build_feedback may call the LLM and take a long time; holding a SQLite write lock
    # during that call causes "database is locked" errors for concurrent requests.
    custom_weights = {"lcce": info["weight_lcce"], "lcc": info["weight_lcc"], "sda": info["weight_sda"]}
    strategies = payload.strategies[: payload.num_schemes]
    if info["weight_preset"] == "custom" and "custom" not in strategies:
        strategies = ["custom"] + strategies

    computed = []
    existing = set()
    timestamp = datetime.now().strftime("%m%d-%H%M")
    for index, strategy in enumerate(strategies):
        result = optimize(ranges, info["orientation"] or "南", strategy, custom_weights, existing)
        seq = existing_count + index + 1
        label = f"{seq:03d}"
        name = f"{project['name']}-方案{label}-{STRATEGY_NAMES.get(strategy, strategy)}"
        feedback = build_feedback(result["params"], result["performance"], info["demand_text"] or "", dict(info))
        computed.append({
            "scheme_id": str(uuid.uuid4()),
            "scheme_name": name,
            "scheme_label": label,
            "strategy": strategy,
            "result": result,
            "feedback": feedback,
        })

    # Step 3: write everything in a single short transaction.
    with get_connection() as conn:
        for item in computed:
            scheme_id = item["scheme_id"]
            result = item["result"]
            feedback = item["feedback"]
            params = result["params"]
            perf = result["performance"]
            conn.execute(
                "INSERT INTO schemes (id, project_id, scheme_name, scheme_label, strategy, description, risk_note, fitness_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (scheme_id, project_id, item["scheme_name"], item["scheme_label"], item["strategy"], result["description"], result["risk_note"], result["fitness_score"]),
            )
            conn.execute(
                "INSERT INTO scheme_params VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scheme_id, params["horizontal_depth"], params["shading_type"], params["material"], params["spacing"], params["h_rotation"], params["v_rotation"], params["blade_depth"], params["window_distance"], params["wwr"], params["glass_type"]),
            )
            conn.execute(
                "INSERT INTO scheme_performance VALUES (?, ?, ?, ?, ?, ?, ?)",
                (scheme_id, perf["lcce"], perf["lcc"], perf["sda"], perf["lcce_rank"], perf["lcc_rank"], perf["sda_rank"]),
            )
            conn.execute(
                "INSERT INTO teaching_feedback VALUES (?, ?, ?, ?, ?, ?)",
                (scheme_id, feedback["key_conflict"], feedback["priority"], feedback["avoid"], feedback["next_step"], feedback["discussion"]),
            )

    return {
        "schemes": [
            {
                "scheme_id": item["scheme_id"],
                "scheme_name": item["scheme_name"],
                "scheme_label": item["scheme_label"],
                "strategy": item["strategy"],
                **item["result"],
            }
            for item in computed
        ]
    }

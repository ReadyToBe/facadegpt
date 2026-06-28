from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
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
STARTER_PROJECT_NAME = "我的第一个外遮阳项目"
STARTER_PROJECT_SEED_KIND = "starter"
DEMO_PROJECT_VERSION = 1
DEMO_PROJECT_SEED_KIND = f"demo_v{DEMO_PROJECT_VERSION}"
DEMO_PROJECT_NAME = "广州办公楼西向立面优化"
EXAMPLE_PROJECT_NAME = STARTER_PROJECT_NAME
LEGACY_EMPTY_PROJECT_NAME = "FacadeGPT 示例项目"

DEMO_DEMAND_TEXT = (
    "广州天河区办公楼，西向立面下午西晒明显，希望降低冷负荷和眩光，"
    "预算中等偏紧，倾向轻质铝合金构件，同时保留较好的办公采光。"
)

DEMO_MESSAGES = [
    {
        "role": "user",
        "content": "广州天河区一栋办公楼，主要是西向立面，下午西晒比较严重。希望在不明显增加预算的情况下控制眩光和冷负荷，同时室内办公区采光不能太差。",
    },
    {
        "role": "assistant",
        "content": (
            "我先把项目边界理解为：广州夏热冬暖气候区、办公建筑、西向立面，核心矛盾是下午低角度太阳带来的眩光与冷负荷，同时不能牺牲太多 sDA。"
            "\n\n建议优先比较竖向遮阳和轻量混合遮阳：竖向构件更适合西晒控制，混合遮阳可以在局部保留水平挑出，帮助削弱高角度直射。"
        ),
    },
    {
        "role": "user",
        "content": "预算中等偏紧，倾向铝合金或轻质构件。外立面希望简洁一些，不要太厚重，窗墙比大概在 60%-70%。",
    },
    {
        "role": "assistant",
        "content": (
            "收到。可以把材料先收敛到铝合金，窗墙比控制在 60%-70% 左右，并把构件间距作为主要调节项。"
            "\n\n下一步我会生成两类方向：一类偏低碳与热负荷控制，另一类偏成本与立面轻量化。两类都保留可读的竖向秩序，便于你在方案详情里继续切换视角和渲染。"
        ),
    },
]

DEMO_PARAMETER_RANGE_OVERRIDES = {
    "shading_type": {"min_val": 2, "max_val": 3},
    "material": {"fixed_val": 2, "is_locked": True},
    "spacing": {"min_val": 400, "max_val": 900},
    "blade_depth": {"min_val": 200, "max_val": 500},
    "window_distance": {"min_val": 100, "max_val": 500},
    "wwr": {"min_val": 50, "max_val": 80},
}

DEMO_SCHEMES = [
    {
        "scheme_label": "001",
        "strategy": "low-carbon",
        "scheme_suffix": "低碳优先",
        "params": {
            "horizontal_depth": 500,
            "shading_type": 2,
            "material": 2,
            "spacing": 800,
            "h_rotation": 0,
            "v_rotation": 10,
            "blade_depth": 200,
            "window_distance": 200,
            "wwr": 70,
            "glass_type": 4,
        },
        "performance": {
            "lcce": 2923.91,
            "lcc": 7201.10,
            "sda": 93.34,
            "lcce_rank": "中",
            "lcc_rank": "中",
            "sda_rank": "优",
        },
        "fitness_score": 0.924,
        "description": "采用 800mm 间距竖向铝合金遮阳，配合三层中空玻璃和 70% 窗墙比，优先控制西向冷负荷与眩光。",
        "risk_note": "竖向构件密度较高时会强化立面秩序，也可能削弱部分侧向视野；建议在室内视角下检查办公区视觉舒适度。",
        "feedback": {
            "key_conflict": "西向低角度太阳控制与室内通透感之间存在拉扯，构件间距是最敏感的调节项。",
            "priority": "优先保留竖向遮阳方向，并在 700-900mm 间距范围内微调，以平衡热负荷、眩光和视野。",
            "avoid": "避免继续加深构件或显著降低窗墙比，否则会让立面过重并压低空间开放感。",
            "next_step": "建议导出室外视角和室内人视角渲染，重点观察下午侧光下的阴影节奏。",
            "discussion": "该方案适合作为低碳控制基准方案，后续可围绕材料截面、构件颜色和局部开启方式深化。",
        },
        "renders": [
            {"view_type": "outdoor", "image_url": "/renders/f7850b1d-8604-4267-bdd4-c912f6fdc4d9.png"},
            {"view_type": "elevation", "image_url": "/renders/095c94a4-b0ba-4a65-ad26-f5b283561f9a.png"},
            {"view_type": "axonometric", "image_url": "/renders/964baba0-c200-4489-a50d-adbf0848e1bd.png"},
        ],
    },
    {
        "scheme_label": "002",
        "strategy": "low-cost",
        "scheme_suffix": "成本优先",
        "params": {
            "horizontal_depth": 600,
            "shading_type": 2,
            "material": 2,
            "spacing": 900,
            "h_rotation": 20,
            "v_rotation": 10,
            "blade_depth": 200,
            "window_distance": 100,
            "wwr": 70,
            "glass_type": 3,
        },
        "performance": {
            "lcce": 2958.07,
            "lcc": 7035.86,
            "sda": 97.34,
            "lcce_rank": "待优化",
            "lcc_rank": "中",
            "sda_rank": "优",
        },
        "fitness_score": 0.933,
        "description": "采用 900mm 间距竖向铝合金遮阳，构件更疏朗，配合双层中空玻璃，降低初始造价和维护复杂度。",
        "risk_note": "构件间距放大后对西晒遮挡会稍弱，后续应重点检查下午低角度日照下的眩光风险。",
        "feedback": {
            "key_conflict": "成本优先方案降低了构件密度，但西晒控制余量也随之减少。",
            "priority": "优先验证 16:00-18:00 的眩光表现；如果仍偏强，可小幅增加竖向叶片转角而不是增加构件数量。",
            "avoid": "不建议直接换成厚重混凝土构件，虽然遮挡更强，但会明显推高自重和立面视觉负担。",
            "next_step": "可以在实验室里固定材料和玻璃类型，只调整间距与转角，观察 LCC 与 sDA 的变化。",
            "discussion": "该方案更像竞赛展示中的经济型对照组，便于说明 FacadeGPT 如何帮助学生比较设计取舍。",
        },
        "renders": [
            {"view_type": "outdoor", "image_url": "/renders/5fa35a00-2d99-4950-ac36-9c7709c2a130.png"},
            {"view_type": "elevation", "image_url": "/renders/32c1d222-16ac-4d42-bd3a-b3773efe2b76.png"},
            {"view_type": "axonometric", "image_url": "/renders/df80e630-a9b4-4588-bb0c-c5af05f2d6a5.png"},
            {"view_type": "indoor", "image_url": "/renders/efa71ea4-dda5-4a04-8cbc-15fa450f32e6.png"},
        ],
    },
]


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


def _insert_project_message(conn, project_id: str, role: str, content: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO project_messages (id, project_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), project_id, role, content, created_at),
    )


def _create_project_record(
    conn,
    user_id: str,
    name: str,
    seed_kind: str = "user",
    created_at: str | None = None,
) -> dict:
    project_id = str(uuid.uuid4())
    now = created_at or datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO projects (id, user_id, name, seed_kind, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, user_id, name, seed_kind, now, now),
    )
    conn.execute("INSERT INTO project_info (project_id) VALUES (?)", (project_id,))
    _insert_ranges(conn, project_id, PARAMETER_DEFAULTS)
    _insert_project_message(conn, project_id, "assistant", PROJECT_WELCOME_MESSAGE, now)
    return {"project_id": project_id, "name": name, "created_at": now, "seed_kind": seed_kind}


def _demo_parameter_ranges() -> list[dict]:
    ranges = [item.copy() for item in PARAMETER_DEFAULTS]
    for item in ranges:
        update = DEMO_PARAMETER_RANGE_OVERRIDES.get(item["param_name"])
        if update:
            item.update(update)
    return ranges


def _demo_seed_base_time(conn, user_id: str) -> datetime:
    row = conn.execute(
        """
        SELECT created_at FROM projects
        WHERE user_id = ? AND COALESCE(seed_kind, 'user') NOT LIKE 'demo_%'
        ORDER BY created_at ASC, rowid ASC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row and row["created_at"]:
        try:
            created_at = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T").replace("Z", ""))
            return created_at - timedelta(minutes=20)
        except ValueError:
            pass
    return datetime.now() - timedelta(minutes=20)


def _create_seed_demo_project(conn, user_id: str) -> dict:
    base_time = _demo_seed_base_time(conn, user_id)
    project_created_at = base_time.isoformat(timespec="seconds")
    project = _create_project_record(
        conn,
        user_id,
        DEMO_PROJECT_NAME,
        seed_kind=DEMO_PROJECT_SEED_KIND,
        created_at=project_created_at,
    )
    project_id = project["project_id"]
    conn.execute(
        """
        UPDATE project_info
        SET location=?, climate_zone=?, building_type=?, orientation=?,
            weight_lcce=?, weight_lcc=?, weight_sda=?, weight_preset=?, demand_text=?
        WHERE project_id=?
        """,
        ("广州", "夏热冬暖", "办公建筑", "西", 0.42, 0.30, 0.28, "custom", DEMO_DEMAND_TEXT, project_id),
    )
    _insert_ranges(conn, project_id, _demo_parameter_ranges())

    last_timestamp = project_created_at
    for index, message in enumerate(DEMO_MESSAGES, start=1):
        timestamp = (base_time + timedelta(minutes=index * 2)).isoformat(timespec="seconds")
        _insert_project_message(conn, project_id, message["role"], message["content"], timestamp)
        last_timestamp = timestamp

    for index, scheme in enumerate(DEMO_SCHEMES):
        scheme_id = str(uuid.uuid4())
        scheme_created_at = base_time + timedelta(minutes=12 + index * 3)
        scheme_timestamp = scheme_created_at.isoformat(timespec="seconds")
        scheme_name = f"{DEMO_PROJECT_NAME}-方案{scheme['scheme_label']}-{scheme['scheme_suffix']}"
        params = scheme["params"]
        perf = scheme["performance"]
        feedback = scheme["feedback"]
        conn.execute(
            """
            INSERT INTO schemes
            (id, project_id, scheme_name, scheme_label, strategy, created_at, description, risk_note, fitness_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scheme_id,
                project_id,
                scheme_name,
                scheme["scheme_label"],
                scheme["strategy"],
                scheme_timestamp,
                scheme["description"],
                scheme["risk_note"],
                scheme["fitness_score"],
            ),
        )
        conn.execute(
            "INSERT INTO scheme_params VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scheme_id,
                params["horizontal_depth"],
                params["shading_type"],
                params["material"],
                params["spacing"],
                params["h_rotation"],
                params["v_rotation"],
                params["blade_depth"],
                params["window_distance"],
                params["wwr"],
                params["glass_type"],
            ),
        )
        conn.execute(
            "INSERT INTO scheme_performance VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                scheme_id,
                perf["lcce"],
                perf["lcc"],
                perf["sda"],
                perf["lcce_rank"],
                perf["lcc_rank"],
                perf["sda_rank"],
            ),
        )
        conn.execute(
            "INSERT INTO teaching_feedback VALUES (?, ?, ?, ?, ?, ?)",
            (
                scheme_id,
                feedback["key_conflict"],
                feedback["priority"],
                feedback["avoid"],
                feedback["next_step"],
                feedback["discussion"],
            ),
        )
        for render_index, render in enumerate(scheme["renders"], start=1):
            render_timestamp = (scheme_created_at + timedelta(seconds=render_index * 20)).isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO render_images
                (id, scheme_id, view_type, image_url, created_at, source_type, status, provider, prompt)
                VALUES (?, ?, ?, ?, ?, 'model_capture', 'completed', 'demo-seed', ?)
                """,
                (
                    str(uuid.uuid4()),
                    scheme_id,
                    render["view_type"],
                    render["image_url"],
                    render_timestamp,
                    f"{DEMO_PROJECT_NAME} {scheme['scheme_suffix']} {render['view_type']} 预制渲染",
                ),
            )
            last_timestamp = render_timestamp

    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (last_timestamp, project_id))
    return project


def _migrate_legacy_empty_seed_projects(conn, user_id: str) -> None:
    rows = conn.execute(
        """
        SELECT p.id,
               COUNT(s.id) AS scheme_count,
               SUM(CASE WHEN pm.role = 'user' THEN 1 ELSE 0 END) AS user_message_count
        FROM projects p
        LEFT JOIN schemes s ON s.project_id = p.id
        LEFT JOIN project_messages pm ON pm.project_id = p.id
        WHERE p.user_id = ? AND p.name = ?
        GROUP BY p.id
        """,
        (user_id, LEGACY_EMPTY_PROJECT_NAME),
    ).fetchall()
    for row in rows:
        if row["scheme_count"] == 0 and (row["user_message_count"] or 0) == 0:
            conn.execute(
                "UPDATE projects SET name = ?, seed_kind = ? WHERE id = ?",
                (STARTER_PROJECT_NAME, STARTER_PROJECT_SEED_KIND, row["id"]),
            )


def _ensure_user_workspace(conn, user_id: str) -> None:
    ensure_user(conn, user_id)
    _migrate_legacy_empty_seed_projects(conn, user_id)

    legacy_count = conn.execute("SELECT COUNT(*) AS count FROM projects WHERE user_id IS NULL").fetchone()["count"]
    if legacy_count:
        conn.execute("UPDATE projects SET user_id = ? WHERE user_id IS NULL", (user_id,))
        conn.execute("UPDATE users SET seed_project_created = 1 WHERE id = ?", (user_id,))

    user = conn.execute(
        "SELECT seed_project_created, demo_seed_version FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    has_regular_project = conn.execute(
        """
        SELECT id FROM projects
        WHERE user_id = ? AND COALESCE(seed_kind, 'user') NOT LIKE 'demo_%'
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    if not has_regular_project and not (user and user["seed_project_created"]):
        _create_project_record(conn, user_id, STARTER_PROJECT_NAME, seed_kind=STARTER_PROJECT_SEED_KIND)
        conn.execute("UPDATE users SET seed_project_created = 1 WHERE id = ?", (user_id,))

    current_demo_version = int(user["demo_seed_version"] or 0) if user else 0
    if current_demo_version < DEMO_PROJECT_VERSION:
        _create_seed_demo_project(conn, user_id)
        conn.execute(
            "UPDATE users SET demo_seed_version = ? WHERE id = ?",
            (DEMO_PROJECT_VERSION, user_id),
        )


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
            SELECT p.id AS project_id, p.name, p.created_at,
                   COALESCE(p.seed_kind, 'user') AS seed_kind,
                   CASE WHEN COALESCE(p.seed_kind, 'user') LIKE 'demo_%' THEN 1 ELSE 0 END AS is_demo,
                   COUNT(s.id) AS scheme_count
            FROM projects p LEFT JOIN schemes s ON s.project_id = p.id
            WHERE p.user_id = ?
            GROUP BY p.id
            ORDER BY CASE WHEN COALESCE(p.seed_kind, 'user') LIKE 'demo_%' THEN 1 ELSE 0 END,
                     p.created_at DESC, p.rowid DESC
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
        project = _require_project(
            conn,
            project_id,
            user_id,
            "id AS project_id, name, created_at, COALESCE(seed_kind, 'user') AS seed_kind",
        )
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

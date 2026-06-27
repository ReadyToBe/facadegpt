from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import current_user_id, ensure_user
from database import get_connection
from services.model_predictor import predict_performance

router = APIRouter(prefix="/api/lab", tags=["lab"])
UserId = Annotated[str, Depends(current_user_id)]

LAB_DEFAULT_PARAMS = {
    "horizontal_depth": 300,
    "shading_type": 2,
    "material": 2,
    "spacing": 500,
    "h_rotation": 0,
    "v_rotation": -30,
    "blade_depth": 200,
    "window_distance": 200,
    "wwr": 50,
    "glass_type": 2,
}

REFERENCE_RANGES = {
    "lcce": {
        "label": "LCCE",
        "unit": "kgCO2/m2",
        "min": 2700.0,
        "max": 3800.0,
        "lower_is_better": True,
    },
    "lcc": {
        "label": "LCC",
        "unit": "yuan/m2",
        "min": 6300.0,
        "max": 10000.0,
        "lower_is_better": True,
    },
    "sda": {
        "label": "sDA",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "lower_is_better": False,
    },
}


class LabParams(BaseModel):
    horizontal_depth: int = Field(LAB_DEFAULT_PARAMS["horizontal_depth"], ge=100, le=600)
    shading_type: int = Field(LAB_DEFAULT_PARAMS["shading_type"], ge=1, le=3)
    material: int = Field(LAB_DEFAULT_PARAMS["material"], ge=1, le=3)
    spacing: int = Field(LAB_DEFAULT_PARAMS["spacing"], ge=100, le=900)
    h_rotation: int = Field(LAB_DEFAULT_PARAMS["h_rotation"], ge=0, le=90)
    v_rotation: int = Field(LAB_DEFAULT_PARAMS["v_rotation"], ge=-90, le=90)
    blade_depth: int = Field(LAB_DEFAULT_PARAMS["blade_depth"], ge=100, le=600)
    window_distance: int = Field(LAB_DEFAULT_PARAMS["window_distance"], ge=100, le=600)
    wwr: int = Field(LAB_DEFAULT_PARAMS["wwr"], ge=20, le=80)
    glass_type: int = Field(LAB_DEFAULT_PARAMS["glass_type"], ge=1, le=4)


class LabEvaluateRequest(BaseModel):
    params: LabParams
    orientation: str | None = "南"


def _model_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _grade_metric(key: str, value: float) -> dict:
    reference = REFERENCE_RANGES[key]
    low = reference["min"]
    high = reference["max"]
    if high <= low:
        score = 1.0
    else:
        score = (value - low) / (high - low)
        if reference["lower_is_better"]:
            score = 1.0 - score
    score = max(0.0, min(1.0, score))
    if score >= 2 / 3:
        grade = "优"
    elif score >= 1 / 3:
        grade = "良"
    else:
        grade = "差"
    return {"grade": grade, "score": round(score, 3)}


def _evaluate(performance: dict) -> dict:
    metrics = {key: _grade_metric(key, float(performance[key])) for key in REFERENCE_RANGES}
    average = sum(item["score"] for item in metrics.values()) / len(metrics)
    if average >= 2 / 3:
        overall = "优"
    elif average >= 1 / 3:
        overall = "良"
    else:
        overall = "差"
    return {
        "overall": {"grade": overall, "score": round(average, 3)},
        "metrics": metrics,
        "basis": "按代际解集图示范围三分位评价：LCCE/LCC 越低越优，sDA 越高越优。",
    }


@router.get("")
def get_lab(user_id: UserId):
    with get_connection() as conn:
        ensure_user(conn, user_id)
        row = conn.execute(
            "SELECT params, performance, evaluations, updated_at FROM user_labs WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return {
            "params": LAB_DEFAULT_PARAMS,
            "performance": None,
            "evaluations": None,
            "reference_ranges": REFERENCE_RANGES,
            "updated_at": None,
        }
    return {
        "params": json.loads(row["params"]),
        "performance": json.loads(row["performance"]) if row["performance"] else None,
        "evaluations": json.loads(row["evaluations"]) if row["evaluations"] else None,
        "reference_ranges": REFERENCE_RANGES,
        "updated_at": row["updated_at"],
    }


@router.post("/evaluate")
def evaluate_lab(payload: LabEvaluateRequest, user_id: UserId):
    params = _model_dict(payload.params)
    performance = predict_performance(params, payload.orientation or "南")
    evaluations = _evaluate(performance)
    updated_at = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        ensure_user(conn, user_id)
        conn.execute(
            """
            INSERT INTO user_labs (user_id, params, performance, evaluations, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                params = excluded.params,
                performance = excluded.performance,
                evaluations = excluded.evaluations,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(params, ensure_ascii=False),
                json.dumps(performance, ensure_ascii=False),
                json.dumps(evaluations, ensure_ascii=False),
                updated_at,
            ),
        )
    return {
        "params": params,
        "performance": performance,
        "evaluations": evaluations,
        "reference_ranges": REFERENCE_RANGES,
        "updated_at": updated_at,
    }

from __future__ import annotations

import itertools
import random

from .model_predictor import fitness, predict_performance_many, rank_performance

STRATEGIES = {
    "balanced": {"weights": {"lcce": 0.33, "lcc": 0.33, "sda": 0.34}, "description": "综合平衡型"},
    "low-carbon": {"weights": {"lcce": 0.6, "lcc": 0.2, "sda": 0.2}, "description": "低碳优先型"},
    "low-cost": {"weights": {"lcce": 0.2, "lcc": 0.6, "sda": 0.2}, "description": "成本优先型"},
    "daylight": {"weights": {"lcce": 0.2, "lcc": 0.2, "sda": 0.6}, "description": "采光优先型"},
}

PARAM_LABELS = {
    "shading_type": {1: "水平遮阳", 2: "垂直遮阳", 3: "混合遮阳"},
    "material": {1: "混凝土", 2: "铝材", 3: "钢材"},
    "glass_type": {1: "单层Low-E", 2: "双层Low-E", 3: "双层中空", 4: "三层中空"},
}


def _values_for_range(item: dict) -> list[int]:
    if item.get("is_locked") and item.get("fixed_val") is not None:
        return [int(item["fixed_val"])]
    start = int(item.get("min_val") or 0)
    end = int(item.get("max_val") or start)
    step = int(item.get("step") or 1)
    return list(range(start, end + 1, step))


def optimize(parameter_ranges: list[dict], orientation: str, strategy: str, custom_weights: dict | None = None, existing: set[tuple] | None = None) -> dict:
    weights = custom_weights if strategy == "custom" and custom_weights else STRATEGIES[strategy]["weights"]
    ranges = {item["param_name"]: _values_for_range(item) for item in parameter_ranges}
    keys = ["horizontal_depth", "shading_type", "material", "spacing", "h_rotation", "v_rotation", "blade_depth", "window_distance", "wwr", "glass_type"]
    sampled_params = []

    random.seed(f"{orientation}-{strategy}-{weights}")
    for _ in range(700):
        params = {key: random.choice(ranges[key]) for key in keys}
        sampled_params.append(params)

    performances = predict_performance_many(sampled_params, orientation)
    bounds = {
        key: (min(perf[key] for perf in performances), max(perf[key] for perf in performances))
        for key in ("lcce", "lcc", "sda")
    }
    candidates = [
        (fitness(perf, weights, bounds), params, perf)
        for params, perf in zip(sampled_params, performances)
    ]

    candidates.sort(key=lambda item: item[0], reverse=True)
    existing = existing or set()
    for score, params, perf in candidates:
        fingerprint = tuple(params[key] for key in keys)
        if fingerprint not in existing:
            existing.add(fingerprint)
            description = (
                f"采用{params['spacing']}mm间距{PARAM_LABELS['shading_type'][params['shading_type']]}，"
                f"{PARAM_LABELS['material'][params['material']]}构件配合{PARAM_LABELS['glass_type'][params['glass_type']]}，"
                f"窗墙比{params['wwr']}%。"
            )
            risk = "遮阳越强越可能压低采光和视野，建议在详情页切换视角检查室内感受。"
            return {
                "params": params,
                "performance": perf | rank_performance(perf),
                "fitness_score": score,
                "description": description,
                "risk_note": risk,
            }
    raise RuntimeError("No candidate found")

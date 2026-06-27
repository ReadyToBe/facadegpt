from __future__ import annotations

from .knowledge_base import format_context, search_knowledge
from .llm_client import OpenAIUnavailable, generate_json, has_openai_key


PARAMETER_DEFAULTS = [
    {"param_name": "horizontal_depth", "param_type": "continuous", "min_val": 100, "max_val": 600, "step": 100, "unit": "mm", "is_locked": False},
    {"param_name": "shading_type", "param_type": "categorical", "options": [{"value": 1, "label": "水平遮阳"}, {"value": 2, "label": "垂直遮阳"}, {"value": 3, "label": "混合"}], "min_val": 1, "max_val": 3, "step": 1, "unit": "--", "is_locked": False},
    {"param_name": "material", "param_type": "categorical", "options": [{"value": 1, "label": "混凝土"}, {"value": 2, "label": "铝材"}, {"value": 3, "label": "钢材"}], "min_val": 1, "max_val": 3, "step": 1, "unit": "--", "is_locked": False},
    {"param_name": "spacing", "param_type": "continuous", "min_val": 100, "max_val": 900, "step": 100, "unit": "mm", "is_locked": False},
    {"param_name": "h_rotation", "param_type": "continuous", "min_val": 0, "max_val": 90, "step": 10, "unit": "deg", "is_locked": False},
    {"param_name": "v_rotation", "param_type": "continuous", "min_val": -90, "max_val": 90, "step": 10, "unit": "deg", "is_locked": False},
    {"param_name": "blade_depth", "param_type": "continuous", "min_val": 100, "max_val": 600, "step": 100, "unit": "mm", "is_locked": False},
    {"param_name": "window_distance", "param_type": "continuous", "min_val": 100, "max_val": 600, "step": 100, "unit": "mm", "is_locked": False},
    {"param_name": "wwr", "param_type": "continuous", "min_val": 20, "max_val": 80, "step": 10, "unit": "%", "is_locked": False},
    {"param_name": "glass_type", "param_type": "categorical", "options": [{"value": 1, "label": "单层Low-E"}, {"value": 2, "label": "双层Low-E"}, {"value": 3, "label": "双层中空"}, {"value": 4, "label": "三层中空"}], "min_val": 1, "max_val": 4, "step": 1, "unit": "--", "is_locked": False},
]


def _contains(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _rule_parse_demand(text: str) -> dict:
    location = "广州" if "广州" in text else "未指定"
    climate_zone = "夏热冬暖" if location == "广州" else "待补充"
    orientation = next((ori for ori in ["南", "北", "东", "西"] if f"{ori}向" in text or f"朝{ori}" in text), "西" if "西晒" in text else "南")
    building_type = "办公建筑" if _contains(text, ["办公", "写字楼"]) else "教学建筑" if _contains(text, ["教学", "校园"]) else "办公建筑"

    weights = {"lcce": 0.33, "lcc": 0.33, "sda": 0.34}
    if _contains(text, ["低碳", "节能", "能耗"]):
        weights = {"lcce": 0.5, "lcc": 0.25, "sda": 0.25}
    if _contains(text, ["成本", "经济", "预算", "不要太高"]):
        weights["lcc"] += 0.18
    if _contains(text, ["采光", "通透", "视野"]):
        weights["sda"] += 0.16
    total = sum(weights.values())
    weights = {key: round(val / total, 2) for key, val in weights.items()}
    weights["sda"] = round(1 - weights["lcce"] - weights["lcc"], 2)

    ranges = [item.copy() for item in PARAMETER_DEFAULTS]
    for item in ranges:
        if item["param_name"] == "shading_type":
            if _contains(text, ["水平遮阳", "横向线条"]):
                item.update({"fixed_val": 1, "is_locked": True})
            elif _contains(text, ["竖向韵律", "垂直", "竖向"]):
                item.update({"fixed_val": 2, "is_locked": True})
            elif _contains(text, ["混合", "综合遮阳"]):
                item.update({"fixed_val": 3, "is_locked": True})
        if item["param_name"] == "spacing" and _contains(text, ["密集", "百叶", "西晒", "遮阳"]):
            item.update({"min_val": 100, "max_val": 400})
        if item["param_name"] == "material" and _contains(text, ["成本", "经济", "不要太高"]):
            item.update({"fixed_val": 2, "is_locked": False})
        if item["param_name"] == "wwr" and _contains(text, ["通透", "采光"]):
            item.update({"min_val": 40, "max_val": 70})

    goals = []
    if _contains(text, ["西晒", "遮阳"]):
        goals.append("控制西晒")
    if _contains(text, ["采光", "通透"]):
        goals.append("保持采光")
    if _contains(text, ["成本", "经济", "预算"]):
        goals.append("控制成本")
    if _contains(text, ["竖向", "韵律"]):
        goals.append("形成竖向立面秩序")

    summary = f"系统理解您正在为{location}{building_type}{orientation}向立面设计建筑表皮，重点是{'、'.join(goals) if goals else '平衡性能与形式'}。已据此推断初始权重并收窄外遮阳参数范围。"
    return {
        "project_info": {
            "location": location,
            "climate_zone": climate_zone,
            "building_type": building_type,
            "orientation": orientation,
            "weights": weights,
        },
        "parameter_ranges": ranges,
        "understanding_summary": summary,
    }


def _normalize_weights(weights: dict) -> dict:
    lcce = max(0, float(weights.get("lcce", 0.33)))
    lcc = max(0, float(weights.get("lcc", 0.33)))
    sda = max(0, float(weights.get("sda", 0.34)))
    total = lcce + lcc + sda or 1
    lcce = round(lcce / total, 2)
    lcc = round(lcc / total, 2)
    sda = round(1 - lcce - lcc, 2)
    return {"lcce": lcce, "lcc": lcc, "sda": sda}


def _apply_llm_result(base: dict, llm_data: dict) -> dict:
    info = base["project_info"]
    incoming = llm_data.get("project_info") or {}
    for key in ("location", "climate_zone", "building_type", "orientation"):
        if incoming.get(key):
            info[key] = incoming[key]
    if incoming.get("weights"):
        info["weights"] = _normalize_weights(incoming["weights"])

    range_updates = llm_data.get("parameter_ranges") or {}
    for item in base["parameter_ranges"]:
        update = range_updates.get(item["param_name"]) or {}
        for key in ("min_val", "max_val", "fixed_val", "is_locked"):
            if key in update:
                item[key] = update[key]

    if llm_data.get("understanding_summary"):
        base["understanding_summary"] = llm_data["understanding_summary"]
    return base


def parse_demand(text: str) -> dict:
    base = _rule_parse_demand(text)
    if not has_openai_key():
        return base

    context = format_context(search_knowledge(text, limit=4))
    schema = """
{
  "project_info": {
    "location": "string",
    "climate_zone": "string",
    "building_type": "string",
    "orientation": "南|北|东|西",
    "weights": {"lcce": 0.33, "lcc": 0.33, "sda": 0.34}
  },
  "parameter_ranges": {
    "shading_type": {"fixed_val": 1, "is_locked": true},
    "spacing": {"min_val": 100, "max_val": 400},
    "wwr": {"min_val": 30, "max_val": 70}
  },
  "understanding_summary": "中文摘要"
}
"""
    system_prompt = (
        "你是建筑表皮设计课程的 AI 助教，负责把学生的自然语言需求解析为结构化项目参数。"
        "只能使用 FacadeGPT 已定义的参数名和取值范围，不要发明新字段。"
        "权重 lcce/lcc/sda 必须非负且总和约等于 1。"
    )
    user_prompt = f"""
学生需求：
{text}

规则解析基线：
{base}

教材检索片段：
{context or "当前未检索到教材片段。"}

请在保留系统参数边界的前提下，修正项目理解、权重和需要锁定/收窄的参数范围。
"""
    try:
        llm_data = generate_json(system_prompt, user_prompt, schema)
        return _apply_llm_result(base, llm_data)
    except (OpenAIUnavailable, ValueError, KeyError, TypeError, OSError, TimeoutError):
        return base

from __future__ import annotations

from .knowledge_base import format_context, search_knowledge
from .llm_client import OpenAIUnavailable, generate_json, has_openai_key


def _rule_feedback(params: dict, perf: dict) -> dict:
    shade = "竖向遮阳" if params["shading_type"] == 2 else "水平遮阳" if params["shading_type"] == 1 else "混合遮阳"
    return {
        "key_conflict": f"{shade}可以降低直射辐射，但过密或过深会牺牲有效日光照度和视野连续性。",
        "priority": f"优先比较百叶间距{params['spacing']}mm、窗墙比{params['wwr']}%与玻璃类型对 LCCE/sDA 的联动影响。",
        "avoid": "避免只用增大玻璃面积追求通透感，这通常会推高西向立面的冷负荷和生命周期成本。",
        "next_step": "建议固定材料不变，分别将百叶间距放宽或窗墙比降低一档，观察三目标曲线如何移动。",
        "discussion": f"当前 sDA 为 {perf['sda']}%。如果业主要求更通透，你愿意接受多少 LCCE 增量来交换采光提升？",
    }


def build_feedback(params: dict, perf: dict, demand_text: str = "", project_info: dict | None = None) -> dict:
    fallback = _rule_feedback(params, perf)
    if not has_openai_key():
        return fallback

    project_info = project_info or {}
    query = " ".join(
        [
            demand_text,
            project_info.get("orientation") or "",
            "building facade shading daylight carbon cost double skin envelope",
        ]
    )
    context_items = search_knowledge(query, limit=5)
    context = format_context(context_items)
    schema = """
{
  "key_conflict": "中文，指出性能矛盾并引用教材页码",
  "priority": "中文，给出优先设计建议",
  "avoid": "中文，指出误区",
  "next_step": "中文，给出下一步对比实验",
  "discussion": "中文，给出课堂讨论问题"
}
"""
    system_prompt = (
        "你是建筑表皮设计课程的专业助教。"
        "请结合方案参数、性能指标和教材片段生成教学反馈。"
        "必须保持批判性和可教学性；如果引用教材，请在句末标注如（Building Skins, pp. 12-13）。"
        "不要编造未出现在教材片段中的页码。"
    )
    user_prompt = f"""
学生原始需求：
{demand_text or "未提供"}

项目信息：
{project_info}

方案参数：
{params}

性能指标：
{perf}

教材片段：
{context or "当前没有可用教材片段，请基于建筑表皮设计常识给出保守反馈。"}
"""
    try:
        data = generate_json(system_prompt, user_prompt, schema)
        return {key: str(data.get(key) or fallback[key]) for key in fallback}
    except (OpenAIUnavailable, ValueError, KeyError, TypeError, OSError, TimeoutError):
        return fallback

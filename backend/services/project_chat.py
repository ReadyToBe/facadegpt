from __future__ import annotations

from .knowledge_base import format_context, search_knowledge
from .llm_client import OpenAIUnavailable, generate_chat, has_openai_key


def respond_to_project_chat(project: dict, project_info: dict, messages: list[dict]) -> str:
    latest_user_message = next(
        (item["content"] for item in reversed(messages) if item.get("role") == "user"),
        "",
    )
    context = format_context(search_knowledge(latest_user_message, limit=4), max_chars=5000)
    project_summary = (
        f"项目：{project.get('name', '未命名项目')}；"
        f"地点：{project_info.get('location') or '待确认'}；"
        f"气候区：{project_info.get('climate_zone') or '待确认'}；"
        f"建筑类型：{project_info.get('building_type') or '待确认'}；"
        f"朝向：{project_info.get('orientation') or '待确认'}。"
    )
    system_prompt = f"""
你是建筑外遮阳设计顾问，正在和用户持续讨论一个真实建筑项目。
你的回答应专业、具体、简洁，并主动帮助用户明确地点、气候、朝向、窗墙比、遮阳形式、材料、预算和采光目标。
不要急于一次性给出最终答案；信息不足时提出一到两个最关键的问题，信息充分时给出可执行的设计建议。
不要声称已经完成模拟或性能计算。引用教材时请在句末标注教材名和页码。

当前项目：
{project_summary}

相关教材片段：
{context or '本轮未检索到直接相关的教材片段，请基于建筑物理常识谨慎回答。'}
""".strip()

    if has_openai_key():
        try:
            return generate_chat(system_prompt, messages[-12:])
        except (OpenAIUnavailable, ValueError, KeyError, TypeError, OSError, TimeoutError):
            pass
    return _fallback_reply(latest_user_message, project_info)


def _fallback_reply(message: str, project_info: dict) -> str:
    known = []
    if project_info.get("location"):
        known.append(f"地点为{project_info['location']}")
    if project_info.get("orientation"):
        known.append(f"主要朝向为{project_info['orientation']}向")
    prefix = f"我先记录到：{'，'.join(known)}。" if known else "我们可以先把设计边界梳理清楚。"
    if any(word in message for word in ("西晒", "西向", "朝西")):
        return prefix + " 西向低角度太阳需要优先比较竖向遮阳或可调节构件。请再告诉我建筑类型、窗墙比和预算倾向。"
    if any(word in message for word in ("采光", "通透", "视野")):
        return prefix + " 采光目标需要和遮阳深度、构件间距一起判断。你更希望保护室内视野，还是优先降低太阳得热？"
    return prefix + " 请继续补充建筑地点、主要朝向、使用功能，以及你最在意的性能目标。"

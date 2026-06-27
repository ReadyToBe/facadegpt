from __future__ import annotations

RENDER_STYLES = [
    {
        "id": "photoreal_day",
        "name": "日景写实",
        "description": "清晰表达材料、遮阳构件和建筑尺度。",
        "prompt": (
            "daytime photorealistic architectural visualization, soft natural sunlight, "
            "accurate facade proportions, realistic aluminium/concrete/glass materials, "
            "clean background, professional architectural portfolio quality"
        ),
    },
    {
        "id": "studio_clay",
        "name": "分析白模",
        "description": "弱化材质，突出构件深度、间距和旋转关系。",
        "prompt": (
            "architectural studio clay model render, white physical model style, "
            "clear shadows showing facade depth, precise louver rhythm, diagrammatic but elegant, "
            "suitable for architectural design analysis"
        ),
    },
    {
        "id": "competition_board",
        "name": "作品集表达",
        "description": "画面清爽完整，适合用于作品集和方案汇报。",
        "prompt": (
            "architectural portfolio style rendering, refined green building facade, "
            "clean composition, high clarity, subtle context, polished academic presentation, "
            "balanced realism and diagrammatic readability"
        ),
    },
    {
        "id": "low_carbon_tech",
        "name": "低碳科技",
        "description": "突出绿色建筑、性能优化和环境技术表达。",
        "prompt": (
            "low-carbon smart facade concept render, high-performance envelope, "
            "subtle green building technology atmosphere, crisp daylight analysis feeling, "
            "professional architectural visualization, restrained futuristic tone"
        ),
    },
    {
        "id": "night_warm",
        "name": "夜景暖光",
        "description": "用于展示立面韵律、通透感和百叶层次。",
        "prompt": (
            "evening architectural visualization, warm interior light behind facade, "
            "clear louver rhythm, elegant shadows, realistic glass reflections, "
            "calm urban context, no crowds"
        ),
    },
]


def render_style_options() -> list[dict]:
    return RENDER_STYLES


def render_style_prompt(style_id_or_text: str) -> str:
    for item in RENDER_STYLES:
        if style_id_or_text in {item["id"], item["name"]}:
            return item["prompt"]
    return style_id_or_text or RENDER_STYLES[0]["prompt"]

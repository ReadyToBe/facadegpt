"""Fixed first message for every newly created FacadeGPT project.

Edit PROJECT_WELCOME_MESSAGE to adjust the introduction shown before the user
sends their first project message.
"""

PROJECT_WELCOME_MESSAGE = """你好，我是 FacadeGPT，你的建筑外遮阳设计助手。

你可以先告诉我项目地点、建筑类型、立面朝向，以及最希望改善的问题，例如遮阳、采光、全生命周期成本（LCC ）或全生命周期碳排放（LCCE）。我会通过对话帮你梳理设计条件。

当条件讨论得差不多时，点击右上角的“生成方案”，我会结合遗传算法，在当前设计条件下，生成 LCCE、LCC 和 sDA综合最优的外遮阳方案。

你可以这样开始：广州办公楼西向立面，希望减少西晒，同时保持良好采光。"""

from .app import ChatApp

__all__ = ["ChatApp", "run"]


def run(agent) -> None:
    """前端统一入口：main.py 通过 run(agent) 启动本界面。"""
    ChatApp(agent).run()

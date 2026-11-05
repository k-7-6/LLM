from .app import ChatApp

__all__ = ["ChatApp", "run"]


def run(agent, config_notice: str | None = None) -> None:
    """前端统一入口：main.py 通过 run(agent, config_notice) 启动本界面。"""
    ChatApp(agent, config_notice=config_notice).run()

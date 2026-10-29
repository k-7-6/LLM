import argparse
import os
import sys
import traceback

# 不生成 __pycache__ 和 .pyc 缓存文件（必须在导入项目模块之前设置）
sys.dont_write_bytecode = True

from core.agent import Agent
from core.config import load_config
from core.skills import discover
from core.tools import configure

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_frontend(name: str):
    """前端工厂：新增 web / desktop / mobile 时，在这里加一行导入即可。"""
    if name == "tui":
        from tui import run
        return run
    raise ValueError(f"未知前端: {name}")


def main() -> None:
    project_root = os.getcwd()  # 启动时的工作目录即项目根目录
    parser = argparse.ArgumentParser(description="ZAgent 智能助手")
    parser.add_argument("--ui", default="tui", choices=("tui",), help="选择前端界面")
    args = parser.parse_args()
    config = load_config()
    skills = discover(project_root)
    configure(config, skills)
    load_frontend(args.ui)(Agent(config, skills=skills))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            input("\n出错了，按回车键关闭窗口...")
        except EOFError:
            pass

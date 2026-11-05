import argparse
import os
import sys
import traceback

# 不生成 __pycache__ 和 .pyc 缓存文件（必须在导入项目模块之前设置）
sys.dont_write_bytecode = True

from core.agent import Agent
from core.config import ensure_config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_frontend(name: str):
    """前端工厂：新增 web / desktop / mobile 时，在这里加一行导入即可。"""
    if name == "tui":
        from tui import run
        return run
    raise ValueError(f"未知前端: {name}")


def resolve_project_root(explicit: str | None, configured: str) -> str:
    """确定项目根目录：--project > ZAGENT_PROJECT_ROOT > config.ini > 当前目录。"""
    candidate = (
        explicit
        or os.environ.get("ZAGENT_PROJECT_ROOT", "").strip()
        or configured
    )
    if not candidate:
        return os.getcwd()
    root = os.path.abspath(os.path.expanduser(candidate))
    if not os.path.isdir(root):
        raise SystemExit(f"项目根目录不存在: {root}")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="ZAgent 智能助手")
    parser.add_argument("--ui", default="tui", choices=("tui",), help="选择前端界面")
    parser.add_argument("--project", help="项目根目录（默认取 config.ini 的 [project] root，否则为当前目录）")
    parser.add_argument("--config", help="配置文件路径（默认查找当前目录的 config.ini）")
    args = parser.parse_args()

    config, created = ensure_config(args.config)
    project_root = resolve_project_root(args.project, config.project_root)
    os.chdir(project_root)  # 让文件工具、.mcp.json、技能都基于项目根目录
    agent = Agent(config, project_root=project_root)
    try:
        load_frontend(args.ui)(agent, config_notice=created)
    finally:
        agent.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            input("\n出错了，按回车键关闭窗口...")
        except EOFError:
            pass

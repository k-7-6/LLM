from . import cli, fetch, files, recall, search, skill, system  # noqa: F401  导入即注册工具
from .registry import catalog, execute, schemas
from .skill import configure as configure_skills

__all__ = ["catalog", "configure", "execute", "schemas"]


def configure(config, skills=(), project_root=None) -> None:
    """把配置文件、启动时发现的技能和项目根目录注入对应工具。"""
    search.configure(config)
    fetch.configure(config)
    cli.configure(config)
    files.configure(config, project_root)
    configure_skills(list(skills), project_root, config)
    recall.configure(project_root, config)

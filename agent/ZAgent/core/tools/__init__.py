from . import cli, fetch, files, search, skill, system  # noqa: F401  导入即注册工具
from .registry import catalog, execute, schemas
from .skill import configure as configure_skills

__all__ = ["catalog", "configure", "execute", "schemas"]


def configure(config, skills=()) -> None:
    """把配置文件和启动时发现的技能注入对应工具。"""
    search.configure(config.search_api_key, config.search_model)
    configure_skills(list(skills))

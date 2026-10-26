from . import cli, fetch, files, search, system  # noqa: F401  导入即注册工具
from .registry import catalog, execute, schemas

__all__ = ["catalog", "configure", "execute", "schemas"]


def configure(config) -> None:
    """把配置文件中的搜索设置注入搜索工具。"""
    search.configure(config.search_api_key, config.search_model)

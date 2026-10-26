import configparser
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    model: str
    search_api_key: str = ""
    search_model: str = "ernie-4.5-turbo-32k"


def load_config(path: str | None = None) -> Config:
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    llm = parser["llm"]
    search = parser["search"] if parser.has_section("search") else {}
    return Config(
        base_url=llm["base_url"],
        api_key=llm["api_key"],
        model=llm["model"],
        search_api_key=search.get("baidu_qianfan_api_key", "").strip(),
        search_model=search.get("baidu_qianfan_model", "ernie-4.5-turbo-32k").strip(),
    )

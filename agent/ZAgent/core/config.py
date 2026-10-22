import configparser
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    model: str


def load_config(path: str | None = None) -> Config:
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    section = parser["llm"]
    return Config(
        base_url=section["base_url"],
        api_key=section["api_key"],
        model=section["model"],
    )

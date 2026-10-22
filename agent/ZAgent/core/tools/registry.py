import json
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], str]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _registry[tool.name] = tool


def schemas() -> list[dict]:
    return [tool.schema() for tool in _registry.values()]


def catalog() -> list[Tool]:
    return list(_registry.values())


def execute(name: str, arguments: str) -> str:
    try:
        return _registry[name].handler(json.loads(arguments or "{}"))
    except Exception as exc:
        return f"错误: {exc}"

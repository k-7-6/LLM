from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """模型流式输出的一个文本片段。"""
    text: str


@dataclass(frozen=True)
class ToolStarted:
    """开始执行一个工具。"""
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolFinished:
    """工具执行完成。"""
    name: str
    result: str


@dataclass(frozen=True)
class Completed:
    """本轮回答结束。"""
    text: str


Event = Token | ToolStarted | ToolFinished | Completed

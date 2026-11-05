from dataclasses import dataclass

from .context import ContextStats


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


@dataclass(frozen=True)
class TurnUsage:
    """一次模型调用的 Token 用量。"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    estimated: bool = False


@dataclass(frozen=True)
class Cancelled:
    """本次输出被用户终止；text 为已经生成的部分内容。"""
    text: str = ""


Event = (
    Token | ToolStarted | ToolFinished | Completed
    | TurnUsage | Cancelled | ContextStats
)

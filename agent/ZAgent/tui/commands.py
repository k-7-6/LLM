"""斜杠命令定义与补全匹配。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str


SLASH_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("/new", "新建会话并自动保存当前会话"),
    SlashCommand("/resume", "打开历史会话列表并恢复"),
    SlashCommand("/save", "保存当前会话"),
    SlashCommand("/compact", "压缩上下文并归档原文"),
    SlashCommand("/status", "查看会话、上下文和 MCP 状态"),
    SlashCommand("/mcp", "查看 MCP 服务器与可用工具"),
    SlashCommand("/help", "显示全部斜杠命令"),
    SlashCommand("/quit", "保存当前会话并退出"),
)

_COMMAND_NAMES = {command.name for command in SLASH_COMMANDS}


def matches(value: str) -> list[SlashCommand]:
    """返回以输入内容为前缀的命令；输入含空格时不再补全。"""
    query = (value or "").strip().lower()
    if not query.startswith("/") or " " in query:
        return []
    return [
        command for command in SLASH_COMMANDS
        if command.name.startswith(query)
    ]


def exact(value: str) -> SlashCommand | None:
    name = (value or "").strip().split(maxsplit=1)[0].lower()
    for command in SLASH_COMMANDS:
        if command.name == name:
            return command
    return None


def command_names() -> set[str]:
    return set(_COMMAND_NAMES)

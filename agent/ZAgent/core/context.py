"""上下文长度估算、压缩归档与检索的公共逻辑。

这里刻意保持简单：不依赖向量数据库或 Embedding，只用字符数估算 Token，
并把完整对话按 JSONL 原样保存到 .agents/context/ 供全文检索。
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

DEFAULT_CONTEXT_WINDOW = 128_000
WARN_RATIO = 0.70
SUMMARY_MAX_TOKENS = 6_000
SUMMARY_TARGET_TOKENS = 5_000
ARCHIVE_DIR = os.path.join(".agents", "context")

COMPACTION_PROMPT_TEMPLATE = """你是一名AI Agent的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便Agent在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约{target_tokens:,}Tokens的Markdown摘要。

摘要应重点保留以下内容：
1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和Agent已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：
- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过recallContext工具重新检索。
- 使用清晰的Markdown结构输出摘要，不要附加解释或无关内容。

最终目标：使一个从未阅读过原始对话的Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。"""

COMPACTION_PROMPT = COMPACTION_PROMPT_TEMPLATE.format(
    target_tokens=SUMMARY_TARGET_TOKENS,
)


def compaction_prompt(target_tokens: int = SUMMARY_TARGET_TOKENS) -> str:
    return COMPACTION_PROMPT_TEMPLATE.format(target_tokens=target_tokens)


@dataclass(frozen=True)
class ContextStats:
    """一次上下文使用量快照，也作为 Agent 事件发给前端。"""

    used: int
    window: int
    percent: float
    default_window: bool
    blocked: bool


@dataclass(frozen=True)
class CompactionResult:
    """一次 /compact 的执行结果。"""

    ok: bool
    archive_id: str = ""
    archive_path: str = ""
    summary_tokens: int = 0
    error: str = ""
    skipped: bool = False
    summary: str = ""


class ContextWindowFullError(RuntimeError):
    """上下文达到阈值后，普通提示词被暂停。"""


def estimate_text_tokens(text: str) -> int:
    """粗略估算文本 Token：英文约 4 字符/token，中文等约 1.5 字符/token。"""
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    other_chars = len(text) - ascii_chars
    return max(1, int(ascii_chars / 4 + other_chars / 1.5))


def message_text(message: dict) -> str:
    """把一条消息的可检索文本拼出来（正文、工具调用参数、工具返回编号）。"""
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif content is not None:
        parts.append(json.dumps(content, ensure_ascii=False))

    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        parts.append(str(function.get("name", "")))
        parts.append(str(function.get("arguments", "")))

    if message.get("tool_call_id"):
        parts.append(str(message["tool_call_id"]))
    return "\n".join(part for part in parts if part)


def estimate_messages_tokens(messages: Iterable[dict]) -> int:
    total = 0
    for message in messages:
        total += 4  # 角色、分隔符等固定开销
        total += estimate_text_tokens(message_text(message))
    return total


def estimate_tools_tokens(tools: list[dict]) -> int:
    if not tools:
        return 0
    return estimate_text_tokens(json.dumps(tools, ensure_ascii=False))


class ContextTracker:
    """记录最近一次 API usage，并在其基础上估算后续新增消息。"""

    def __init__(self, window: int | None = None,
                 default_window: int = DEFAULT_CONTEXT_WINDOW,
                 warn_ratio: float = WARN_RATIO):
        self.window = window or default_window
        self.default_window = not window
        self.warn_ratio = warn_ratio
        self._usage_total: int | None = None
        self._anchor = 0

    def record_usage(self, usage, anchor: int) -> None:
        total = _usage_total(usage)
        if total is None:
            return
        self._usage_total = total
        self._anchor = anchor

    def reset(self) -> None:
        self._usage_total = None
        self._anchor = 0

    def stats(self, messages: list[dict], tool_tokens: int = 0) -> ContextStats:
        if self._usage_total is None:
            used = estimate_messages_tokens(messages) + tool_tokens
        else:
            used = self._usage_total + estimate_messages_tokens(
                messages[self._anchor:]
            )
        percent = used / self.window * 100 if self.window else 0.0
        return ContextStats(
            used=used,
            window=self.window,
            percent=percent,
            default_window=self.default_window,
            blocked=percent >= self.warn_ratio * 100,
        )


def _usage_total(usage) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            total = (usage.get("prompt_tokens") or 0) + (
                usage.get("completion_tokens") or 0
            )
    else:
        total = getattr(usage, "total_tokens", None)
        if total is None:
            total = (getattr(usage, "prompt_tokens", 0) or 0) + (
                getattr(usage, "completion_tokens", 0) or 0
            )
    try:
        total = int(total)
    except (TypeError, ValueError):
        return None
    return total if total > 0 else None


def archive_directory(project_root: str, directory: str = ARCHIVE_DIR) -> str:
    return os.path.join(os.path.abspath(project_root), directory)


def _next_archive_id(directory: str) -> str:
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base
    counter = 2
    while os.path.exists(os.path.join(directory, candidate + ".jsonl")):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def save_archive(project_root: str, messages: list[dict],
                 archive_dir: str = ARCHIVE_DIR) -> tuple[str, str]:
    """把完整原始上下文按消息顺序写入 JSONL，成功后才返回。"""
    directory = archive_directory(project_root, archive_dir)
    os.makedirs(directory, exist_ok=True)
    archive_id = _next_archive_id(directory)
    path = os.path.join(directory, archive_id + ".jsonl")

    try:
        with open(path, "x", encoding="utf-8", newline="\n") as file:
            for message in messages:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        if os.path.getsize(path) <= 0:
            raise OSError("归档文件为空")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return archive_id, path


def read_archive(path: str) -> list[dict]:
    """读取压缩前保存的 JSONL 归档；跳过损坏或非对象行。"""
    messages: list[dict] = []
    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                messages.append(message)
    return messages


def render_transcript(messages: list[dict]) -> str:
    """把消息转成适合交给摘要模型的纯文本记录。"""
    lines: list[str] = []
    for index, message in enumerate(messages, 1):
        role = message.get("role", "unknown")
        lines.append(f"### [{index}] {role}")
        content = message.get("content")
        if content is not None:
            lines.append(str(content))
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            lines.append(f"[工具调用] {function.get('name', '')}")
            lines.append(f"[参数] {function.get('arguments', '')}")
        if message.get("tool_call_id"):
            lines.append(f"[tool_call_id] {message['tool_call_id']}")
        lines.append("")
    return "\n".join(lines)


def archive_note(archive_id: str, when: str) -> str:
    return (
        f"此前上下文已于{when}完成压缩，原始上下文保存在编号为"
        f"{archive_id}的归档文件中。如需查找历史信息，请使用recallContext工具。"
    )

import os
import threading
from datetime import datetime
from typing import Callable, Iterator

from .config import Config
from .context import (
    compaction_prompt,
    CompactionResult,
    ContextStats,
    ContextTracker,
    ContextWindowFullError,
    archive_note,
    estimate_messages_tokens,
    estimate_text_tokens,
    estimate_tools_tokens,
    render_transcript,
    save_archive,
)
from .events import (
    Cancelled,
    Completed,
    Event,
    Token,
    ToolFinished,
    ToolStarted,
    TurnUsage,
)
from .llm import LLMClient
from .mcp import McpManager, McpSnapshot
from .sessions import (
    AGENTS_MARKER,
    SessionInfo,
    SessionRecord,
    SessionStore,
    SessionSwitch,
)
from .skills import Skill, discover, system_prompt
from .tools import configure, execute, schemas


class Agent:
    """对话编排：消息历史、流式输出、工具调用。与界面完全解耦。"""

    def __init__(self, config: Config, llm: LLMClient | None = None,
                 skills: list[Skill] | None = None,
                 mcp_errors: list[str] | None = None,
                 project_root: str | None = None,
                 autoload: bool = True):
        self.config = config
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.autoload = autoload
        self._initial_mcp_errors = list(mcp_errors or [])
        self._mcp: McpManager | None = None
        self._mcp_snapshot: McpSnapshot | None = None
        self._mcp_listener: Callable[[McpSnapshot], None] | None = None
        self.mcp_autostart = autoload and mcp_errors is None

        if skills is None and autoload:
            skills = discover(
                self.project_root,
                config.skills_dir,
                config.skill_file,
            )
        self.skills: list[Skill] = list(skills or [])
        configure(config, self.skills, self.project_root)

        self._llm = llm or LLMClient(config)
        self.messages: list[dict] = []

        # 压缩时只替换对话历史，System Prompt 需要保留原始版本（含技能说明）。
        self._base_system_prompt = system_prompt(self.skills)
        if self._base_system_prompt:
            self.messages.append({
                "role": "system",
                "content": self._base_system_prompt,
            })

        self._store = SessionStore(
            self.project_root,
            config.sessions_dir,
            config.session_title_length,
        )
        self._session: SessionRecord | None = None
        self._session_error = ""
        self._agents_md_message: dict | None = None
        self._agents_md_path = ""

        self._context = ContextTracker(
            config.context_window or None,
            default_window=config.default_context_window,
            warn_ratio=config.context_warn_ratio,
        )
        self._compacting = False
        self._cancel_event: threading.Event | None = None
        # 保证同一时刻只执行一个任务或一次压缩，压缩期间不会误跑工具。
        self._lock = threading.Lock()

        # 会话首次加载：若项目根目录存在 AGENTS.md，则注入一次并持久化。
        self._load_agents_md(record=True)

        if self.mcp_autostart:
            self.start_mcp()

    def close(self) -> None:
        """关闭由 Agent 自动建立的 MCP 连接。"""
        if self._mcp is not None:
            self._mcp.close()
            self._mcp = None

    @property
    def model(self) -> str:
        return self._llm.model

    @property
    def agents_md_path(self) -> str:
        return self._agents_md_path

    @property
    def agents_md_active(self) -> bool:
        return self._agents_md_message is not None

    @property
    def session_error(self) -> str:
        return self._session_error

    @property
    def mcp_errors(self) -> list[str]:
        if self._mcp is not None:
            return list(self._mcp.snapshot().errors)
        return list(self._initial_mcp_errors)

    def mcp_snapshot(self) -> McpSnapshot:
        if self._mcp is not None:
            return self._mcp.snapshot()
        config_path = os.path.join(
            self.project_root, self.config.mcp_config_file,
        )
        return McpSnapshot(
            configured=os.path.isfile(config_path),
            loading=False,
            config_path=config_path,
            errors=tuple(self._initial_mcp_errors),
        )

    def start_mcp(self,
                  on_update: Callable[[McpSnapshot], None] | None = None) -> None:
        """异步连接 MCP；立即返回，状态通过回调或 mcp_snapshot() 获取。"""
        if on_update is not None:
            self._mcp_listener = on_update
        if self._mcp is not None:
            if self._mcp_listener is not None:
                self._mcp_listener(self._mcp.snapshot())
            return
        self._mcp = McpManager(
            self.project_root,
            config_file=self.config.mcp_config_file,
            connect_timeout=self.config.mcp_connect_timeout,
            call_timeout=self.config.mcp_call_timeout,
            max_tool_name_length=self.config.mcp_max_tool_name_length,
            on_update=self._on_mcp_update,
        )
        self._mcp.start_async()

    def set_mcp_listener(
            self, listener: Callable[[McpSnapshot], None] | None) -> None:
        self._mcp_listener = listener
        if self._mcp is not None and listener is not None:
            listener(self._mcp.snapshot())

    def _on_mcp_update(self, snapshot: McpSnapshot) -> None:
        self._mcp_snapshot = snapshot
        listener = self._mcp_listener
        if listener is not None:
            listener(snapshot)

    # ---------- 会话 ----------

    def current_session(self) -> SessionInfo | None:
        if self._session is None:
            return None
        return self._session.info()

    def list_sessions(self) -> list[SessionInfo]:
        return self._store.list()

    def save_session(self) -> SessionInfo | None:
        """保存当前会话；没有会话时创建一个空会话并保存。"""
        try:
            record = self._ensure_session()
            record.save()
            return record.info()
        except OSError as exc:
            self._session_error = f"保存会话失败: {exc}"
            return None

    def new_session(self) -> SessionSwitch:
        """保存当前会话，然后开启一个全新的会话。"""
        saved: SessionInfo | None = None
        if self._session is not None:
            try:
                self._session.save()
                saved = self._session.info()
            except OSError as exc:
                self._session_error = f"保存会话失败: {exc}"

        try:
            record = self._store.create()
        except OSError as exc:
            raise RuntimeError(f"创建新会话失败: {exc}") from exc

        self._session = record
        self._session_error = ""
        self.messages = []
        if self._base_system_prompt:
            self.messages.append({
                "role": "system",
                "content": self._base_system_prompt,
            })
        self._agents_md_message = None
        self._agents_md_path = ""
        self._context.reset()
        self._load_agents_md(record=True)
        return SessionSwitch(
            action="new",
            session=record.info(),
            saved=saved,
        )

    def resume_session(self, session_id: str) -> SessionSwitch | None:
        """载入历史会话；会话不存在时返回 None。"""
        if self._compacting:
            raise RuntimeError("上下文压缩进行中，暂时不能切换会话")
        if self._lock.locked():
            raise RuntimeError("当前已有任务正在执行，请先等待任务完成")

        data = self._store.load(session_id)
        if data is None:
            return None

        saved: SessionInfo | None = None
        if self._session is not None:
            try:
                self._session.save()
                saved = self._session.info()
            except OSError as exc:
                self._session_error = f"保存当前会话失败: {exc}"

        self._session = SessionRecord(
            self._store, data.info.id, data.info.path,
        )
        if data.uses_snapshot:
            self.messages = list(data.messages)
        else:
            self.messages = []
            if self._base_system_prompt:
                self.messages.append({
                    "role": "system",
                    "content": self._base_system_prompt,
                })
            self.messages.extend(data.messages)

        self._agents_md_message = data.agents_message
        self._agents_md_path = _agents_path(data.agents_message)
        self._session_error = ""
        self._context.reset()
        return SessionSwitch(
            action="resumed",
            session=data.info,
            saved=saved,
        )

    def _ensure_session(self) -> SessionRecord:
        if self._session is None:
            self._session = self._store.create()
        return self._session

    def _write_message(self, message: dict, ensure: bool = False) -> None:
        try:
            record = self._ensure_session() if ensure else self._session
            if record is not None:
                record.record_message(message)
        except OSError as exc:
            self._session_error = f"写入会话事件失败: {exc}"

    def _append_message(self, message: dict, ensure: bool = False) -> None:
        self.messages.append(message)
        self._write_message(message, ensure=ensure)

    def _load_agents_md(self, record: bool) -> None:
        """读取 AGENTS.md 并作为一条固定 system 消息注入当前会话。"""
        filename = self.config.agents_file or "AGENTS.md"
        path = filename
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        if not os.path.isfile(path):
            return

        try:
            with open(path, encoding="utf-8-sig") as file:
                text = file.read(self.config.file_max_read_chars + 1)
        except (OSError, UnicodeDecodeError) as exc:
            self._session_error = f"读取 {filename} 失败: {exc}"
            return
        if not text.strip():
            return
        if len(text) > self.config.file_max_read_chars:
            text = (
                text[:self.config.file_max_read_chars].rstrip()
                + "\n\n…（AGENTS.md 过长，已截断）"
            )

        try:
            relative = os.path.relpath(path, self.project_root)
        except ValueError:
            relative = filename
        relative = relative.replace(os.sep, "/")
        content = (
            f"{AGENTS_MARKER}\n"
            "# 项目约定（AGENTS.md）\n\n"
            f"以下内容来自项目根目录的 `{relative}`，"
            "在本次会话中必须遵守：\n\n"
            f"{text}"
        )
        message = {"role": "system", "content": content}
        self.messages.append(message)
        self._agents_md_message = message
        self._agents_md_path = relative

        if record:
            try:
                record_handle = self._ensure_session()
                record_handle.record_agents_md(relative, message)
            except OSError as exc:
                self._session_error = f"写入 AGENTS.md 会话事件失败: {exc}"

    # ---------- 对话 ----------

    def context_stats(self) -> ContextStats:
        """当前上下文用量：System Prompt、历史消息、工具消息与工具定义。"""
        return self._context.stats(
            self.messages,
            estimate_tools_tokens(schemas()),
        )

    def ask(self, prompt: str,
            cancel: threading.Event | None = None) -> Iterator[Event]:
        """执行一轮任务；cancel 置位后会在下一个流式片段处停止输出。"""
        if self._compacting:
            raise RuntimeError("上下文压缩进行中，暂时不能处理新的任务")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("当前已有任务正在执行，请稍后再试")
        self._cancel_event = cancel or threading.Event()
        try:
            yield from self._ask(prompt)
        finally:
            self._cancel_event = None
            self._lock.release()

    def cancel(self) -> bool:
        """请求终止当前输出；没有正在执行的任务时返回 False。"""
        event = self._cancel_event
        if event is None:
            return False
        event.set()
        return True

    def _ask(self, prompt: str) -> Iterator[Event]:
        stats = self.context_stats()
        if stats.blocked:
            raise ContextWindowFullError(
                f"上下文已使用 {stats.percent:.1f}%，请先执行 /compact 压缩上下文"
            )

        cancel = self._cancel_event

        def cancelled() -> bool:
            return cancel is not None and cancel.is_set()

        if cancelled():
            yield Cancelled()
            return

        self._append_message(
            {"role": "user", "content": prompt}, ensure=True,
        )
        tools = schemas()
        tool_tokens = estimate_tools_tokens(tools)

        while True:
            if cancelled():
                yield Cancelled()
                return

            reply = ""
            calls = {}
            usage = None
            prompt_tokens = estimate_messages_tokens(self.messages) + tool_tokens
            stream = self._llm.stream_chat(self.messages, tools)

            try:
                for chunk in stream:
                    if cancelled():
                        break
                    # 开启 stream_options 后，usage 通常出现在 choices 为空的最后一块。
                    if getattr(chunk, "usage", None) is not None:
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        reply += delta.content
                        yield Token(delta.content)
                    for tc in delta.tool_calls or []:
                        call = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            call["id"] = tc.id
                        if tc.function.name:
                            call["name"] += tc.function.name
                        if tc.function.arguments:
                            call["arguments"] += tc.function.arguments
            finally:
                if cancelled():
                    close = getattr(stream, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass

            if cancelled():
                # 只保留完整的正文，丢弃可能只收到一半的工具调用参数。
                if reply:
                    self._append_message({"role": "assistant", "content": reply})
                if usage is not None:
                    self._context.record_usage(usage, len(self.messages))
                yield self._turn_usage(usage, reply, prompt_tokens)
                yield self.context_stats()
                yield Cancelled(reply)
                return

            if not calls:
                self._append_message({"role": "assistant", "content": reply})
                self._context.record_usage(usage, len(self.messages))
                yield self._turn_usage(usage, reply, prompt_tokens)
                yield self.context_stats()
                yield Completed(reply)
                return

            self._append_message({
                "role": "assistant",
                "content": reply or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls.values()
                ],
            })
            self._context.record_usage(usage, len(self.messages))
            yield self._turn_usage(usage, reply, prompt_tokens)
            yield self.context_stats()

            pending = list(calls.values())
            for index, call in enumerate(pending):
                if cancelled():
                    # 为未执行的工具补上结果，避免历史里留下悬空的 tool_calls。
                    for remaining in pending[index:]:
                        self._append_message({
                            "role": "tool",
                            "tool_call_id": remaining["id"],
                            "content": "错误: 用户终止了本次输出，工具未执行。",
                        })
                    yield self.context_stats()
                    yield Cancelled()
                    return
                yield ToolStarted(call["name"], call["arguments"])
                result = execute(call["name"], call["arguments"])
                yield ToolFinished(call["name"], result)
                self._append_message({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })
            yield self.context_stats()

    @staticmethod
    def _turn_usage(usage, reply: str, prompt_tokens: int) -> TurnUsage:
        """把 API usage 转成前端可显示的事件；缺 usage 时退回估算。"""
        if usage is not None:
            def number(name: str) -> int:
                try:
                    return int(getattr(usage, name, 0) or 0)
                except (TypeError, ValueError):
                    return 0

            prompt = number("prompt_tokens") or prompt_tokens
            completion = number("completion_tokens")
            total = number("total_tokens") or prompt + completion

            cached = 0
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                cached = int(getattr(details, "cached_tokens", 0) or 0)
            if not cached:
                cached = number("prompt_cache_hit_tokens")

            reasoning = 0
            details = getattr(usage, "completion_tokens_details", None)
            if details is not None:
                reasoning = int(getattr(details, "reasoning_tokens", 0) or 0)

            return TurnUsage(
                prompt, completion, total,
                cached_tokens=cached,
                reasoning_tokens=reasoning,
            )

        completion = estimate_text_tokens(reply)
        return TurnUsage(
            prompt_tokens, completion, prompt_tokens + completion, estimated=True,
        )

    def compact(self) -> CompactionResult:
        """归档完整上下文，再让模型生成摘要并替换历史。

        任何一步失败都保留原有 messages，只返回错误，用户可以重试 /compact。
        """
        if self._compacting:
            return CompactionResult(False, error="上下文压缩正在进行")
        if not any(message.get("role") != "system" for message in self.messages):
            return CompactionResult(True, skipped=True)
        if not self._lock.acquire(blocking=False):
            return CompactionResult(
                False, error="当前已有任务正在执行，请等待任务完成后再压缩"
            )

        self._compacting = True
        try:
            # 必须先成功保存原始上下文，之后才允许压缩或替换。
            try:
                archive_id, archive_path = save_archive(
                    self.project_root,
                    self.messages,
                    self.config.archive_dir,
                )
            except Exception as exc:
                return CompactionResult(False, error=f"保存原始上下文失败: {exc}")

            try:
                summary, _usage = self._llm.complete(
                    [
                        {
                            "role": "system",
                            "content": compaction_prompt(
                                self.config.summary_target_tokens,
                            ),
                        },
                        {
                            "role": "user",
                            "content": "以下是需要压缩的历史上下文：\n\n"
                                       + render_transcript(self.messages),
                        },
                    ],
                    max_tokens=self.config.summary_max_tokens,
                )
                summary = (summary or "").strip()
                if not summary:
                    raise ValueError("模型返回了空摘要")

                when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                system = self._compose_system(summary, archive_note(archive_id, when))
                self.messages = [{"role": "system", "content": system}]
                if self._agents_md_message is not None:
                    # AGENTS.md 固定在系统摘要之后，后续轮次原样复用。
                    self.messages.append(self._agents_md_message)
                self._context.reset()
                self._record_snapshot()
                return CompactionResult(
                    True,
                    archive_id=archive_id,
                    archive_path=archive_path,
                    summary_tokens=estimate_text_tokens(summary),
                    summary=summary,
                )
            except Exception as exc:
                return CompactionResult(
                    False,
                    archive_id=archive_id,
                    archive_path=archive_path,
                    error=f"生成摘要失败: {exc}",
                )
        finally:
            self._compacting = False
            self._lock.release()

    def _record_snapshot(self) -> None:
        if self._session is None:
            return
        try:
            self._session.record_snapshot(self.messages)
        except OSError as exc:
            self._session_error = f"写入会话快照失败: {exc}"

    def _compose_system(self, summary: str, note: str) -> str:
        sections: list[str] = []
        if self._base_system_prompt:
            sections.append(self._base_system_prompt)
        sections.append("## 历史上下文摘要\n\n" + summary)
        sections.append("> " + note)
        return "\n\n---\n\n".join(sections)


def _agents_path(message: dict | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, str):
        return ""
    for line in content.splitlines():
        if line.startswith("以下内容来自项目根目录的 `"):
            return line.removeprefix("以下内容来自项目根目录的 `").split("`", 1)[0]
    return ""

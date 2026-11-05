"""会话事件日志：把对话消息按 JSONL 追加保存，支持保存与恢复。"""

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime

DEFAULT_SESSIONS_DIR = os.path.join(".agents", "sessions")
SESSION_VERSION = 1
AGENTS_MARKER = "<!-- ZAgent AGENTS.md -->"
_ID_PATTERN = re.compile(r"[0-9A-Za-z_-]{1,64}")


@dataclass(frozen=True)
class SessionInfo:
    id: str
    path: str
    title: str
    created_at: str
    updated_at: str
    messages: int
    has_agents_md: bool = False


@dataclass
class SessionData:
    info: SessionInfo
    messages: list[dict] = field(default_factory=list)
    agents_message: dict | None = None
    uses_snapshot: bool = False


@dataclass(frozen=True)
class SessionSwitch:
    """一次 /new 或 /resume 的结果，供界面显示提示。"""

    action: str
    session: SessionInfo
    saved: SessionInfo | None = None


class SessionRecord:
    """当前会话的写入句柄；每条消息立即追加到事件日志。"""

    def __init__(self, store: "SessionStore", session_id: str, path: str):
        self.store = store
        self.id = session_id
        self.path = path

    def record_agents_md(self, filename: str, message: dict) -> None:
        self._append({
            "type": "agents_md",
            "path": filename,
            "message": message,
        })

    def record_message(self, message: dict) -> None:
        self._append({"type": "message", "message": message})

    def record_snapshot(self, messages: list[dict]) -> None:
        self._append({"type": "snapshot", "messages": messages})

    def save(self) -> None:
        """显式保存标记，并把已有事件刷到磁盘。"""
        self._append({"type": "saved"}, sync=True)

    def info(self) -> SessionInfo:
        return self.store._read_info(self.path) or SessionInfo(
            id=self.id,
            path=self.path,
            title="（无标题）",
            created_at="",
            updated_at="",
            messages=0,
        )

    def _append(self, event: dict, sync: bool = False) -> None:
        event = dict(event)
        event.setdefault("ts", _now())
        self.store.append(self.path, event, sync=sync)


class SessionStore:
    """管理 <项目根>/.agents/sessions 下的会话 JSONL 文件。"""

    def __init__(self, project_root: str,
                 directory: str = DEFAULT_SESSIONS_DIR,
                 title_length: int = 40):
        self.project_root = os.path.abspath(project_root)
        self.directory = os.path.join(self.project_root, directory)
        self.title_length = title_length
        self._lock = threading.Lock()

    def create(self) -> SessionRecord:
        os.makedirs(self.directory, exist_ok=True)
        session_id = _next_id(self.directory)
        path = os.path.join(self.directory, session_id + ".jsonl")
        event = {
            "type": "meta",
            "version": SESSION_VERSION,
            "id": session_id,
            "created_at": _now(),
            "project_root": self.project_root,
        }
        with self._lock:
            with open(path, "x", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
        return SessionRecord(self, session_id, path)

    def append(self, path: str, event: dict, sync: bool = False) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._lock:
            with open(path, "a", encoding="utf-8", newline="\n") as file:
                file.write(line)
                file.flush()
                if sync:
                    os.fsync(file.fileno())

    def list(self) -> list[SessionInfo]:
        if not os.path.isdir(self.directory):
            return []
        infos: list[SessionInfo] = []
        for name in sorted(os.listdir(self.directory), reverse=True):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(self.directory, name)
            info = self._read_info(path)
            if info is not None and info.messages > 0:
                infos.append(info)
        infos.sort(key=lambda item: (item.updated_at, item.id), reverse=True)
        return infos

    def load(self, session_id: str) -> SessionData | None:
        if not _ID_PATTERN.fullmatch(session_id or ""):
            return None
        path = os.path.join(self.directory, session_id + ".jsonl")
        if not os.path.isfile(path):
            return None
        events = _read_events(path)
        if not events:
            return None

        meta = next(
            (event for event in events if event.get("type") == "meta"), {},
        )
        if not meta:
            return None

        messages: list[dict] = []
        agents_message: dict | None = None
        uses_snapshot = False
        for event in events:
            kind = event.get("type")
            if kind == "agents_md":
                message = event.get("message")
                if isinstance(message, dict):
                    agents_message = message
                    if not uses_snapshot:
                        messages.append(message)
            elif kind == "message":
                message = event.get("message")
                if isinstance(message, dict):
                    messages.append(message)
            elif kind == "snapshot":
                snapshot = event.get("messages")
                if isinstance(snapshot, list):
                    messages = [
                        dict(item) for item in snapshot if isinstance(item, dict)
                    ]
                    uses_snapshot = True
                    agents_message = _find_agents_message(messages) or agents_message

        if uses_snapshot:
            agents_message = _find_agents_message(messages) or agents_message

        info = _info_from_events(
            path, events, meta, messages, agents_message, self.title_length,
        )
        return SessionData(
            info=info,
            messages=messages,
            agents_message=agents_message,
            uses_snapshot=uses_snapshot,
        )

    def _read_info(self, path: str) -> SessionInfo | None:
        events = _read_events(path)
        if not events:
            return None
        meta = next(
            (event for event in events if event.get("type") == "meta"), None,
        )
        if meta is None:
            return None

        messages: list[dict] = []
        agents_message: dict | None = None
        uses_snapshot = False
        for event in events:
            kind = event.get("type")
            if kind == "agents_md":
                message = event.get("message")
                if isinstance(message, dict):
                    agents_message = message
                    if not uses_snapshot:
                        messages.append(message)
            elif kind == "message":
                message = event.get("message")
                if isinstance(message, dict):
                    messages.append(message)
            elif kind == "snapshot":
                snapshot = event.get("messages")
                if isinstance(snapshot, list):
                    messages = [
                        dict(item) for item in snapshot if isinstance(item, dict)
                    ]
                    uses_snapshot = True
                    agents_message = _find_agents_message(messages) or agents_message
        return _info_from_events(
            path, events, meta, messages, agents_message, self.title_length,
        )


def _info_from_events(path: str, events: list[dict], meta: dict,
                      messages: list[dict], agents_message: dict | None,
                      title_length: int) -> SessionInfo:
    conversation = [
        message for message in messages if message.get("role") != "system"
    ]
    title = ""
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            title = " ".join(content.split())
        elif content is not None:
            title = " ".join(json.dumps(content, ensure_ascii=False).split())
        if title:
            break
    if not title:
        title = "（无标题）"
    if len(title) > title_length:
        title = title[: title_length - 1] + "…"

    created = str(meta.get("created_at") or "")
    updated = ""
    for event in events:
        stamp = event.get("ts")
        if isinstance(stamp, str) and stamp:
            updated = stamp
    if not updated:
        try:
            updated = datetime.fromtimestamp(os.path.getmtime(path)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError:
            updated = created

    return SessionInfo(
        id=str(meta.get("id") or os.path.basename(path)[:-6]),
        path=path,
        title=title,
        created_at=created,
        updated_at=updated,
        messages=len(conversation),
        has_agents_md=agents_message is not None,
    )


def _find_agents_message(messages: list[dict]) -> dict | None:
    for message in messages:
        if message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.lstrip().startswith(AGENTS_MARKER):
            return message
    return None


def _read_events(path: str) -> list[dict]:
    events: list[dict] = []
    try:
        with open(path, encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except OSError:
        return []
    return events


def _next_id(directory: str) -> str:
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base
    counter = 2
    while os.path.exists(os.path.join(directory, candidate + ".jsonl")):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

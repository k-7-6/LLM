"""MCP Client：读取项目 .mcp.json，连接 Streamable HTTP 服务器并注册远程工具。

MCP SDK 是异步的，而 Agent 的工具执行是同步的。这里用一个后台事件循环线程
持有到各服务器的长连接，同步侧通过 run_coroutine_threadsafe 调用。
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams

from .tools.registry import Tool, catalog, register

logger = logging.getLogger(__name__)

CONFIG_FILE = ".mcp.json"
CONNECT_TIMEOUT = 20.0
CALL_TIMEOUT = 60.0
MAX_NAME_LENGTH = 64

_FUNCTION_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]")
SUPPORTED_TYPES = {"streamable_http", "streamable-http", "http"}


@dataclass(frozen=True)
class McpServer:
    name: str
    url: str


def load_mcp_servers(path: str) -> tuple[dict[str, McpServer], list[str]]:
    """解析 .mcp.json，返回有效服务器与配置错误。"""
    if not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"读取 {path} 失败: {exc}"]

    raw_servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(raw_servers, dict):
        return {}, [f"{path} 缺少 mcpServers 配置"]

    servers: dict[str, McpServer] = {}
    errors: list[str] = []
    for name, raw in raw_servers.items():
        if not isinstance(raw, dict):
            errors.append(f"MCP Server '{name}' 配置必须是对象")
            continue
        url = raw.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"MCP Server '{name}' 缺少 url")
            continue
        kind = str(raw.get("type", "streamable_http")).strip().lower()
        if kind not in SUPPORTED_TYPES:
            errors.append(
                f"MCP Server '{name}' 使用了不支持的 type '{kind}'，仅支持 streamable_http"
            )
            continue
        servers[name] = McpServer(name=name, url=url.strip())
    return servers, errors


class McpManager:
    """管理 MCP 连接，并把远程工具注册进本地工具注册表。"""

    def __init__(self, project_root: str):
        self.config_path = os.path.join(project_root, CONFIG_FILE)
        self.errors: list[str] = []
        self.connected: list[str] = []
        self.exposed_tools: dict[str, tuple[str, str]] = {}

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="mcp-event-loop", daemon=True,
        )
        self._started = False
        self._sessions: dict[str, ClientSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, concurrent.futures.Future] = {}

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def connect(self) -> None:
        """连接全部服务器并注册工具；单个服务器失败不影响其他服务器。"""
        servers, config_errors = load_mcp_servers(self.config_path)
        self.errors.extend(config_errors)
        if not servers:
            return

        self._thread.start()
        self._started = True

        ready: dict[str, concurrent.futures.Future] = {}
        for name, server in servers.items():
            signal = concurrent.futures.Future()
            ready[name] = signal
            self._tasks[name] = asyncio.run_coroutine_threadsafe(
                self._serve(server, signal), self._loop,
            )

        entries = []
        for name, signal in ready.items():
            try:
                result = signal.result(timeout=CONNECT_TIMEOUT + 5)
            except Exception as exc:
                self.errors.append(
                    f"MCP Server '{name}' ({servers[name].url}) 连接失败: "
                    f"{_describe(exc)}"
                )
                self._tasks[name].cancel()
                continue
            self.connected.append(name)
            for tool in result:
                entries.append((name, tool))

        for (server_name, tool), exposed in zip(
            entries, self._allocate_names(entries)
        ):
            self._register(server_name, tool, exposed)

    async def _serve(self, server: McpServer,
                     signal: concurrent.futures.Future) -> None:
        try:
            async with streamable_http_client(server.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), CONNECT_TIMEOUT)
                    tools = await self._list_tools(session)
                    stop = asyncio.Event()
                    self._sessions[server.name] = session
                    self._locks[server.name] = asyncio.Lock()
                    self._stop_events[server.name] = stop
                    if not signal.done():
                        signal.set_result(tools)
                    await stop.wait()
        except Exception as exc:
            if not signal.done():
                signal.set_exception(exc)
            else:
                logger.warning("MCP Server %s 连接中断: %s", server.name, exc)
        finally:
            self._sessions.pop(server.name, None)
            self._locks.pop(server.name, None)
            self._stop_events.pop(server.name, None)

    async def _list_tools(self, session: ClientSession) -> list:
        tools = []
        cursor = None
        for _ in range(100):  # 防御异常的无限分页
            params = PaginatedRequestParams(cursor=cursor) if cursor else None
            result = await asyncio.wait_for(
                session.list_tools(params=params), CONNECT_TIMEOUT,
            )
            tools.extend(result.tools)
            cursor = getattr(result, "next_cursor", None)
            if not cursor:
                break
        return tools

    def _allocate_names(self, entries) -> list[str]:
        """未冲突时保留原工具名，冲突或名称非法时加服务器前缀。"""
        reserved = {tool.name for tool in catalog()}
        counts = Counter(tool.name for _, tool in entries)
        allocated: list[str] = []

        for server_name, tool in entries:
            original = tool.name
            base = original if _FUNCTION_NAME.fullmatch(original) else _sanitize(original)
            if counts[original] > 1 or base in reserved:
                base = _prefix(server_name, original)
            candidate = base
            index = 2
            while candidate in reserved:
                suffix = f"_{index}"
                candidate = base[:MAX_NAME_LENGTH - len(suffix)] + suffix
                index += 1
            reserved.add(candidate)
            allocated.append(candidate)
        return allocated

    def _register(self, server_name: str, tool, exposed: str) -> None:
        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
        parameters = {key: value for key, value in schema.items() if key != "$schema"}
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})

        description = tool.description or tool.name
        register(Tool(
            name=exposed,
            description=f"[MCP:{server_name}] {description}",
            parameters=parameters,
            handler=self._handler(exposed),
        ))
        self.exposed_tools[exposed] = (server_name, tool.name)

    def _handler(self, exposed: str):
        def handler(arguments: dict) -> str:
            return self.call_tool(exposed, arguments)
        return handler

    def call_tool(self, exposed: str, arguments: dict) -> str:
        target = self.exposed_tools.get(exposed)
        if target is None:
            return f"错误: 未找到 MCP 工具 '{exposed}'"
        server_name, tool_name = target

        session = self._sessions.get(server_name)
        lock = self._locks.get(server_name)
        if session is None or lock is None:
            return f"错误: MCP Server '{server_name}' 当前未连接"

        async def invoke():
            async with lock:
                return await session.call_tool(tool_name, arguments or {})

        future = asyncio.run_coroutine_threadsafe(invoke(), self._loop)
        try:
            result = future.result(timeout=CALL_TIMEOUT)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return f"错误: 调用 MCP 工具 '{exposed}' 超时（{CALL_TIMEOUT:.0f} 秒）"
        except Exception as exc:
            return (f"错误: 调用 MCP Server '{server_name}' 的工具 "
                    f"'{tool_name}' 失败: {_describe(exc)}")
        return format_result(result)

    def close(self) -> None:
        if not self._started or not self._thread.is_alive():
            return
        for event in list(self._stop_events.values()):
            try:
                self._loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass
        for future in list(self._tasks.values()):
            try:
                future.result(timeout=5)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


def format_result(result) -> str:
    """把 MCP 返回的文本、结构化数据和资源整理成工具消息。"""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            parts.append(block.text)
        elif kind == "image":
            parts.append(f"[图片 {block.mime_type}，{len(block.data)} 字符 base64]")
        elif kind == "audio":
            parts.append(f"[音频 {block.mime_type}，{len(block.data)} 字符 base64]")
        elif kind == "resource_link":
            parts.append(f"[资源链接 {block.name}: {block.uri}]")
        elif kind == "resource":
            resource = block.resource
            if getattr(resource, "text", None) is not None:
                parts.append(resource.text)
            elif getattr(resource, "blob", None) is not None:
                parts.append(f"[二进制资源 {resource.uri}，{len(resource.blob)} 字符]")
            else:
                parts.append(f"[资源 {resource.uri}]")
        else:
            parts.append(str(block))

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        parts.append("结构化数据:\n" + json.dumps(
            structured, ensure_ascii=False, indent=2,
        ))

    text = "\n".join(part for part in parts if part) or "（无返回内容）"
    return f"错误: {text}" if getattr(result, "is_error", False) else text


def _sanitize(value: str) -> str:
    clean = _INVALID_CHARS.sub("_", value).strip("_") or "tool"
    return clean[:MAX_NAME_LENGTH]


def _prefix(server_name: str, tool_name: str) -> str:
    prefix = _sanitize(server_name)
    room = MAX_NAME_LENGTH - len(prefix) - 1
    return f"{prefix}_{_sanitize(tool_name)[:max(room, 1)]}"


def _describe(exc: Exception, depth: int = 0) -> str:
    """展开 ExceptionGroup，给出最内层、可读的错误原因。"""
    group = getattr(exc, "exceptions", None)
    if isinstance(group, (list, tuple)) and group and depth < 5:
        return _describe(group[0], depth + 1)
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__

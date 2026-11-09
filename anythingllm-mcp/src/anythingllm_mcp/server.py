"""MCP tools for querying and managing an AnythingLLM instance."""

from __future__ import annotations

import logging

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent

from .client import AnythingLLMClient, AnythingLLMError
from .config import Config

logger = logging.getLogger(__name__)


def _text(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _error(text: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        is_error=True,
    )


def make_ask_workspace(config: Config, client: AnythingLLMClient):
    async def ask_workspace(message: str, mode: str = "query") -> CallToolResult:
        """Ask the workspace knowledge base; `mode` is query, chat, or automatic."""
        if not message.strip():
            return _error("message must be non-empty")

        try:
            body = await client.chat(config.workspace_slug, message, mode)
        except AnythingLLMError as exc:
            logger.warning("ask_workspace failed: %s", exc)
            return _error(str(exc))

        answer = body.get("textResponse") or ""
        return CallToolResult(
            content=[TextContent(type="text", text=answer)],
            structured_content={
                "textResponse": answer,
                "sources": body.get("sources") or [],
            },
        )

    return ask_workspace


def make_list_workspaces(client: AnythingLLMClient):
    async def list_workspaces() -> CallToolResult:
        """List all AnythingLLM workspaces with their names and slugs."""
        try:
            workspaces = await client.list_workspaces()
        except AnythingLLMError as exc:
            logger.warning("list_workspaces failed: %s", exc)
            return _error(str(exc))

        if not workspaces:
            return _text("（当前没有任何工作区）")

        summary = []
        lines = ["当前工作区："]
        for ws in workspaces:
            name = str(ws.get("name") or "(未命名)")
            slug = str(ws.get("slug") or ws.get("id") or "")
            summary.append({"name": name, "slug": slug})
            lines.append(f"- {name} — slug: {slug or '(无)'}")

        return CallToolResult(
            content=[TextContent(type="text", text="\n".join(lines))],
            structured_content={"workspaces": summary},
        )

    return list_workspaces


def make_create_workspace(client: AnythingLLMClient):
    async def create_workspace(name: str) -> CallToolResult:
        """Create a new workspace; `name` is its human-readable label."""
        name = name.strip()
        if not name:
            return _error("name must be non-empty")

        try:
            workspace = await client.create_workspace(name)
        except AnythingLLMError as exc:
            logger.warning("create_workspace failed: %s", exc)
            return _error(str(exc))

        label = str(workspace.get("name") or name)
        slug = str(workspace.get("slug") or workspace.get("id") or "")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"已创建工作区 '{label}'（slug: {slug or '(无)'}）",
                )
            ],
            structured_content={"name": label, "slug": slug},
        )

    return create_workspace


def make_upload_document(config: Config, client: AnythingLLMClient):
    async def upload_document(
        file_path: str, workspace_slug: str = ""
    ) -> CallToolResult:
        """Upload a local file and embed it into a workspace.

        `file_path` must be reachable from the machine running this MCP server.
        `workspace_slug` defaults to ANYTHINGLLM_WORKSPACE_SLUG.
        """
        path = file_path.strip()
        if not path:
            return _error("file_path must be non-empty")
        slug = workspace_slug.strip() or config.workspace_slug

        try:
            body = await client.upload_document(path, slug)
        except AnythingLLMError as exc:
            logger.warning("upload_document failed: %s", exc)
            return _error(str(exc))

        documents = [d for d in body.get("documents") or [] if isinstance(d, dict)]
        locations = [str(d["location"]) for d in documents if d.get("location")]

        lines = [f"已上传 {path}，并提交到工作区 {slug}。"]
        if locations:
            lines.append("已索引文档：")
            lines.extend(f"- {location}" for location in locations)
        else:
            lines.append("上传接口未返回文档位置，请在工作区文档列表中确认。")

        return CallToolResult(
            content=[TextContent(type="text", text="\n".join(lines))],
            structured_content={"workspace": slug, "documents": locations},
        )

    return upload_document


def create_server(config: Config) -> tuple[MCPServer, AnythingLLMClient]:
    config.validate()
    server = MCPServer(
        name="anythingllm-mcp",
        title="AnythingLLM MCP",
        description="Query and manage AnythingLLM workspaces via MCP",
        version="0.2.0",
    )

    client = AnythingLLMClient(config)
    server.add_tool(
        make_ask_workspace(config, client),
        name="ask_workspace",
        description=(
            "向 AnythingLLM 工作区的知识库提问，返回基于工作区内已索引文档生成的回答。"
            "mode 可选：query（仅依据工作区文档回答，默认）、chat（允许使用模型自身知识）、"
            "automatic（自动判断）。适用于查询工作区资料中记载的事实。"
        ),
        structured_output=False,
    )
    server.add_tool(
        make_list_workspaces(client),
        name="list_workspaces",
        description=(
            "列出 AnythingLLM 中所有工作区，返回工作区名称与 slug。"
            "需要知道有哪些工作区、或确认新建工作区的 slug 时使用。"
        ),
        structured_output=False,
    )
    server.add_tool(
        make_create_workspace(client),
        name="create_workspace",
        description=(
            "在 AnythingLLM 中创建一个新工作区。name 为工作区显示名称，"
            "返回新工作区的 slug，可接着用于 upload_document 或 ask_workspace。"
        ),
        structured_output=False,
    )
    server.add_tool(
        make_upload_document(config, client),
        name="upload_document",
        description=(
            "上传本机文件到 AnythingLLM 并加入指定工作区的知识库（自动向量化）。"
            "file_path 必须是运行本 MCP 服务的机器上可访问的路径；"
            "workspace_slug 省略时使用 ANYTHINGLLM_WORKSPACE_SLUG。"
            "支持的格式取决于 AnythingLLM 后端配置（常见：pdf、docx、txt、md、csv）。"
        ),
        structured_output=False,
    )
    return server, client

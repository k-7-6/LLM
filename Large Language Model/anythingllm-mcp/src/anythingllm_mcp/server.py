"""MCP server with a single tool that queries an AnythingLLM workspace."""

from __future__ import annotations

import logging

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent

from .client import AnythingLLMClient, AnythingLLMError
from .config import Config

logger = logging.getLogger(__name__)

TOOL_NAME = "ask_workspace"
TOOL_DESCRIPTION = (
    "向 AnythingLLM 工作区的知识库提问，返回基于工作区内已索引文档生成的回答。"
    "mode 可选：query（仅依据工作区文档回答，默认）、chat（允许使用模型自身知识）、"
    "automatic（自动判断）。适用于查询工作区资料中记载的事实。"
)


def _make_tool(config: Config, client: AnythingLLMClient):
    async def ask_workspace(message: str, mode: str = "query") -> CallToolResult:
        """Ask the workspace knowledge base; `mode` is query, chat, or automatic."""
        if not message.strip():
            return CallToolResult(
                content=[TextContent(type="text", text="message must be non-empty")],
                is_error=True,
            )

        try:
            body = await client.chat(config.workspace_slug, message, mode)
        except AnythingLLMError as exc:
            logger.warning("ask_workspace failed: %s", exc)
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                is_error=True,
            )

        answer = body.get("textResponse") or ""
        return CallToolResult(
            content=[TextContent(type="text", text=answer)],
            structured_content={
                "textResponse": answer,
                "sources": body.get("sources") or [],
            },
        )

    return ask_workspace


def create_server(config: Config) -> tuple[MCPServer, AnythingLLMClient]:
    server = MCPServer(
        name="anythingllm-mcp",
        title="AnythingLLM MCP",
        description="Query a single AnythingLLM workspace via MCP",
        version="0.1.0",
    )

    client = AnythingLLMClient(config)
    server.add_tool(
        _make_tool(config, client),
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        structured_output=False,
    )
    return server, client

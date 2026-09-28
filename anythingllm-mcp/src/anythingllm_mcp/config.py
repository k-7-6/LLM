"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_WORKSPACE_SLUG = "a53fa77f-02ae-454b-9bc4-6abab2321218"


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    workspace_slug: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    request_timeout: float

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            base_url=os.environ.get(
                "ANYTHINGLLM_BASE_URL", "http://localhost:3001/api"
            ).rstrip("/"),
            api_key=os.environ.get(
                "ANYTHINGLLM_API_KEY", "MBVDT4X-53GM44N-J7V353G-9CZCDFF"
            ),
            workspace_slug=os.environ.get(
                "ANYTHINGLLM_WORKSPACE_SLUG", DEFAULT_WORKSPACE_SLUG
            ),
            mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            mcp_path=os.environ.get("MCP_PATH", "/mcp"),
            request_timeout=float(os.environ.get("MCP_REQUEST_TIMEOUT", "60.0")),
        )

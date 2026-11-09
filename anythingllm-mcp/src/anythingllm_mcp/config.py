"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_WORKSPACE_SLUG = "a53fa77f-02ae-454b-9bc4-6abab2321218"


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


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
            api_key=os.environ.get("ANYTHINGLLM_API_KEY", ""),
            workspace_slug=os.environ.get(
                "ANYTHINGLLM_WORKSPACE_SLUG", DEFAULT_WORKSPACE_SLUG
            ),
            mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            mcp_path=os.environ.get("MCP_PATH", "/mcp"),
            request_timeout=float(os.environ.get("MCP_REQUEST_TIMEOUT", "60.0")),
        )

    def validate(self) -> None:
        """Fail fast with a local, actionable message instead of a remote 401."""
        if not self.api_key.strip():
            raise ConfigError(
                "未设置 ANYTHINGLLM_API_KEY。请先在 AnythingLLM 的 Settings → "
                "API Keys 中生成密钥，再以环境变量 ANYTHINGLLM_API_KEY 启动 MCP 服务。"
            )
        if not self.base_url:
            raise ConfigError("ANYTHINGLLM_BASE_URL 不能为空")
        if not self.mcp_path.startswith("/"):
            raise ConfigError("MCP_PATH 必须以 / 开头，例如 /mcp")

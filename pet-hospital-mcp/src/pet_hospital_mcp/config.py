"""Configuration for the Pet Hospital MCP service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Immutable configuration loaded from environment variables."""

    pet_hospital_base_url: str
    mcp_host: str
    mcp_port: int
    mcp_path: str
    request_timeout: float
    max_retries: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            pet_hospital_base_url=os.environ.get(
                "PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080"
            ).rstrip("/"),
            mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            mcp_path=os.environ.get("MCP_PATH", "/mcp"),
            request_timeout=float(os.environ.get("MCP_REQUEST_TIMEOUT", "10.0")),
            max_retries=int(os.environ.get("MCP_MAX_RETRIES", "2")),
        )

    @property
    def mcp_url(self) -> str:
        """Return the full MCP endpoint URL."""
        return f"http://{self.mcp_host}:{self.mcp_port}{self.mcp_path}"

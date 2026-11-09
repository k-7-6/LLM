"""Minimal HTTP client for the AnythingLLM developer API."""

from __future__ import annotations

import mimetypes
import os

import httpx

from .config import Config


class AnythingLLMError(Exception):
    """Raised when the AnythingLLM backend cannot answer."""


class AnythingLLMClient:
    def __init__(
        self,
        config: Config,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.request_timeout, connect=10.0),
            headers={"Authorization": f"Bearer {config.api_key}"},
            transport=transport,
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Send a request and normalize transport/HTTP/JSON errors."""
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise AnythingLLMError("AnythingLLM request timed out")
        except httpx.HTTPError as exc:
            raise AnythingLLMError(f"AnythingLLM unreachable: {exc}")

        if resp.status_code != 200:
            raise AnythingLLMError(
                f"AnythingLLM returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            body = resp.json()
        except ValueError:
            raise AnythingLLMError("AnythingLLM returned non-JSON response")

        if isinstance(body, dict) and body.get("error"):
            raise AnythingLLMError(str(body["error"]))
        if not isinstance(body, dict):
            raise AnythingLLMError("AnythingLLM returned an unexpected payload")
        return body

    async def chat(self, slug: str, message: str, mode: str) -> dict:
        """Send a prompt to a workspace and return the raw chat payload."""
        return await self._request(
            "POST",
            f"/v1/workspace/{slug}/chat",
            json={"message": message, "mode": mode},
        )

    async def list_workspaces(self) -> list[dict]:
        """Return every workspace visible to the configured API key."""
        body = await self._request("GET", "/v1/workspaces")
        workspaces = body.get("workspaces")
        if not isinstance(workspaces, list):
            raise AnythingLLMError(
                "AnythingLLM returned an unexpected workspaces payload"
            )
        return [ws for ws in workspaces if isinstance(ws, dict)]

    async def create_workspace(self, name: str) -> dict:
        """Create a workspace and return its object."""
        body = await self._request(
            "POST", "/v1/workspace/new", json={"name": name}
        )
        workspace = body.get("workspace")
        if not isinstance(workspace, dict):
            raise AnythingLLMError(
                "AnythingLLM returned an unexpected workspace payload"
            )
        return workspace

    async def upload_document(
        self, file_path: str, workspace_slug: str = ""
    ) -> dict:
        """Upload a local file and optionally embed it into a workspace."""
        try:
            with open(file_path, "rb") as fh:
                content = fh.read()
        except OSError as exc:
            raise AnythingLLMError(f"无法读取文件 {file_path}: {exc}")

        data: dict[str, str] = {}
        if workspace_slug:
            data["addToWorkspaces"] = workspace_slug

        filename = os.path.basename(file_path)
        mime, _ = mimetypes.guess_type(filename)
        files = {"file": (filename, content, mime or "application/octet-stream")}

        body = await self._request(
            "POST", "/v1/document/upload", data=data, files=files
        )
        if body.get("success") is False:
            raise AnythingLLMError(str(body.get("message") or "文档上传失败"))
        return body

    async def close(self) -> None:
        await self._client.aclose()

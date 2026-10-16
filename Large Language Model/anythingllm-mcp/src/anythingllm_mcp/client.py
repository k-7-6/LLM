"""Minimal HTTP client for the AnythingLLM developer API."""

from __future__ import annotations

import httpx

from .config import Config


class AnythingLLMError(Exception):
    """Raised when the AnythingLLM backend cannot answer."""


class AnythingLLMClient:
    def __init__(self, config: Config) -> None:
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.request_timeout, connect=10.0),
            headers={"Authorization": f"Bearer {config.api_key}"},
        )

    async def chat(self, slug: str, message: str, mode: str) -> dict:
        """Send a prompt to a workspace and return the raw chat payload."""
        try:
            resp = await self._client.post(
                f"/v1/workspace/{slug}/chat",
                json={"message": message, "mode": mode},
            )
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

        if body.get("error"):
            raise AnythingLLMError(str(body["error"]))
        return body

    async def close(self) -> None:
        await self._client.aclose()

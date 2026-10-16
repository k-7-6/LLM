"""REST client for the Pet Hospital Go API."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import Config
from .errors import ErrorCode, ToolError

logger = logging.getLogger(__name__)

_PETS_PATH = "/api/v1/pets"


class RestError(Exception):
    """Base exception for REST client errors."""


class BackendTimeout(RestError):
    """Raised when the backend times out."""


class BackendUnavailable(RestError):
    """Raised when the backend is unreachable."""


class BackendApiError(RestError):
    """Raised when the backend returns a non-2xx status."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Backend API error {status_code}: {message}")


class InvalidResponse(RestError):
    """Raised when the backend returns malformed JSON."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class PetHospitalClient:
    """Async HTTP client for the Pet Hospital Go REST API."""

    def __init__(self, config: Config) -> None:
        self._base_url = config.pet_hospital_base_url
        self._timeout = httpx.Timeout(timeout=config.request_timeout, connect=5.0)
        self._max_retries = config.max_retries
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            follow_redirects=True,
        )

    async def list_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call GET /api/v1/pets with the given query parameters.

        Raises:
            BackendTimeout: on request timeout.
            BackendUnavailable: on connection errors.
            BackendApiError: on non-2xx responses.
            InvalidResponse: on malformed JSON.
        """
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(
                    _PETS_PATH,
                    params=params,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("code") != 200 or "data" not in body:
                        raise InvalidResponse(
                            f"Unexpected response structure: {body}"
                        )
                    return body["data"]
                if resp.status_code == 408 or resp.status_code == 504:
                    last_exc = BackendTimeout()
                    continue
                if 400 <= resp.status_code < 600:
                    detail = ""
                    try:
                        err_body = resp.json()
                        detail = err_body.get("message", str(err_body))
                    except Exception:
                        detail = resp.text[:200]
                    last_exc = BackendApiError(resp.status_code, detail)
                    continue
                # Retry on 5xx
                last_exc = BackendApiError(resp.status_code, resp.text[:200])
            except httpx.TimeoutException:
                last_exc = BackendTimeout()
            except httpx.ConnectError:
                last_exc = BackendUnavailable()
            except httpx.NetworkError:
                last_exc = BackendUnavailable()

        if last_exc is None:
            last_exc = BackendUnavailable()
        raise last_exc

    async def health_check(self) -> dict[str, Any]:
        """Call GET /health on the backend."""
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise BackendTimeout()
        except httpx.ConnectError:
            raise BackendUnavailable()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

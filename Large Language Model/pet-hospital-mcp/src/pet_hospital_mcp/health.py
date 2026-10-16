"""Health check and tool discovery endpoints."""

from __future__ import annotations

import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.rest_client import PetHospitalClient

logger = logging.getLogger(__name__)


async def _health(request: Request, cfg: Config, cli: PetHospitalClient) -> JSONResponse:
    """Return service health status."""
    try:
        backend_health = await cli.health_check()
        return JSONResponse({
            "status": "healthy",
            "service": "pet-hospital-mcp",
            "backend": backend_health.get("status", "unknown"),
            "mcp_endpoint": cfg.mcp_url,
        })
    except Exception as exc:
        return JSONResponse(
            {"status": "unhealthy", "service": "pet-hospital-mcp", "error": str(exc)},
            status_code=503,
        )


def create_app(config: Config) -> Starlette:
    """Create the Starlette application with /health endpoint."""
    client = PetHospitalClient(config)

    async def health(request: Request) -> JSONResponse:
        return await _health(request, config, client)

    return Starlette(
        routes=[
            Route("/health", endpoint=health, methods=["GET"]),
        ],
    )

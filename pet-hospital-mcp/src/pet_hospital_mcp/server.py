"""MCP server setup for the Pet Hospital service."""

from __future__ import annotations

import logging

from mcp.server import MCPServer
from starlette.applications import Starlette
from starlette.routing import Mount

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.tools.list_pets import TOOL_DESCRIPTION, TOOL_NAME, _make_tool_func

logger = logging.getLogger(__name__)


def create_server(config: Config) -> tuple[MCPServer, Starlette]:
    """Create and configure the MCP server with all registered tools.

    Returns a tuple of (mcpserver, combined_app) where combined_app includes
    both the MCP endpoint and the /health endpoint.
    """
    server = MCPServer(
        name="pet-hospital-mcp",
        title="Pet Hospital MCP",
        description="MCP service exposing the Pet Hospital Go REST API",
        version="1.0.0",
    )

    rest_client = PetHospitalClient(config)
    tool_fn = _make_tool_func(config, rest_client)

    server.add_tool(
        tool_fn,
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        structured_output=False,
    )

    # Mount the MCP app into a combined Starlette app
    mcp_app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host=config.mcp_host,
    )

    # Add /health route
    from pet_hospital_mcp.health import create_app as health_app_factory
    health_app = health_app_factory(config)

    combined = Starlette(
        routes=[
            Mount("/", app=mcp_app),
            *health_app.routes,
        ],
    )

    return server, combined

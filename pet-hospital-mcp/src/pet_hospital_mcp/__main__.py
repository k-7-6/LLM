"""Entry point for the Pet Hospital MCP service."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.logging_config import setup_logging
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.server import create_server

logger = logging.getLogger(__name__)


async def _run(config: Config) -> None:
    """Start the MCP server and manage its lifecycle."""
    rest_client = PetHospitalClient(config)
    server, app = create_server(config)

    # Graceful shutdown
    stop = asyncio.get_event_loop().create_future()

    def _handle_signal() -> None:
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal())

    logger.info(
        "Starting Pet Hospital MCP server",
        extra={
            "host": config.mcp_host,
            "port": config.mcp_port,
            "path": config.mcp_path,
            "mcp_url": config.mcp_url,
        },
    )

    try:
        await server.run_streamable_http_async(
            host=config.mcp_host,
            port=config.mcp_port,
            streamable_http_path=config.mcp_path,
            stateless_http=True,
            json_response=True,
        )
    except asyncio.CancelledError:
        logger.info("Server shutting down")
    finally:
        await rest_client.close()


def main() -> None:
    """CLI entry point."""
    config = Config.from_env()
    setup_logging()
    logger.info("Config loaded: %s", config)

    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(0)


if __name__ == "__main__":
    main()

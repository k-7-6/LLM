"""Entry point: run the MCP server over Streamable HTTP."""

from __future__ import annotations

import asyncio
import logging

from .config import Config
from .server import create_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _run(config: Config) -> None:
    server, client = create_server(config)
    logger.info("MCP endpoint: http://%s:%s%s", config.mcp_host, config.mcp_port, config.mcp_path)
    try:
        await server.run_streamable_http_async(
            host=config.mcp_host,
            port=config.mcp_port,
            streamable_http_path=config.mcp_path,
            stateless_http=True,
            json_response=True,
        )
    finally:
        await client.close()


def main() -> None:
    asyncio.run(_run(Config.from_env()))


if __name__ == "__main__":
    main()

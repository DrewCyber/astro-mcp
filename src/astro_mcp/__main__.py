"""Entry point: python -m astro_mcp."""

import asyncio

from astro_mcp.config import settings


def main() -> None:
    """Run the MCP server: stdio by default, streamable-HTTP via configuration."""
    if settings.transport == "http":
        from astro_mcp.http_server import run_http

        run_http()
        return

    from astro_mcp.server import _run

    asyncio.run(_run())


if __name__ == "__main__":
    main()

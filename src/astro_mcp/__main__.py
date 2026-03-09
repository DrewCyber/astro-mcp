"""Entry point: python -m astro_mcp."""

import asyncio


def main() -> None:
    """Run the MCP server via stdio transport."""
    from astro_mcp.server import _run
    asyncio.run(_run())


if __name__ == "__main__":
    main()


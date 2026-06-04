"""Stdio entry point for the QueryWise MCP server.

Lets any stdio-capable MCP client (Claude Code, Claude Desktop, Cursor,
GitHub Copilot, Codex, ChatGPT custom connectors, …) spawn QueryWise as a
subprocess and talk to it over JSON-RPC on stdin/stdout — no HTTP, no
HTTPS, no tunnel required.

The stdio server still talks to the same Postgres backing the running
FastAPI app, so changes made from Claude show up immediately in the web
UI (and vice versa). Make sure DATABASE_URL points at a running app DB
before launching.

Installed as the `querywise-mcp` console script (see pyproject.toml).
Invoke directly with:

    querywise-mcp

Or, without installing, from the backend/ directory:

    python -m app.mcp.stdio
"""

import logging
import sys


def main() -> None:
    """Run the MCP server over stdio.

    Logs go to stderr so they don't corrupt the JSON-RPC stream on stdout.
    """
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Only our own logs at INFO — third-party libs stay at WARNING.
    logging.getLogger("querywise").setLevel(logging.INFO)

    # Imported lazily so logging is configured before SQLAlchemy/FastMCP
    # initialize their own loggers.
    from app.mcp.server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

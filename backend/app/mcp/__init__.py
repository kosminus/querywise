"""MCP server exposing QueryWise over the Model Context Protocol.

Mounted on the FastAPI app under /mcp (streamable HTTP transport) by main.py.
"""

from app.mcp.server import mcp, mount_mcp

__all__ = ["mcp", "mount_mcp"]

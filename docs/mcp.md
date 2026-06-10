# Using QueryWise from Claude / Cursor / Copilot / Codex (MCP)

QueryWise exposes its semantic layer and query pipeline as an **MCP server**, with two transports:

- **HTTP** at `http://localhost:8000/mcp` (streamable HTTP, mounted on the backend).
- **stdio** via the `querywise-mcp` console script (runs as a subprocess, talks to the same Postgres).

Both modes expose the same 24 tools — `add_metric`, `add_glossary_term`, `list_connections`, `get_semantic_context`, `generate_sql`, `run_sql`, `ask`, `query_history`, etc. — and share the same backing store as the REST API and the web UI.

`DATABASE_URL` is only the QueryWise metadata database. It stores connection
records, schema cache, glossary terms, metrics, dictionary entries, knowledge,
sample queries, and query history. User databases are added separately with the
`create_connection` MCP tool, the web UI, or the REST API.

For any PostgreSQL target connection, use a connection string that is reachable
from the process running the MCP server:

| MCP transport | Where it runs | Target DB hostname must be reachable from |
|---------------|---------------|-------------------------------------------|
| HTTP `http://localhost:8000/mcp` | `backend` container | Docker/backend network |
| Docker stdio via `docker compose exec backend querywise-mcp` | `backend` container | Docker/backend network |
| Local stdio via `querywise-mcp` | Host machine | Host machine |

External PostgreSQL databases work normally as long as firewall, DNS, SSL, and
credentials allow access from that location. For example, if QueryWise/MCP runs
inside Docker and the database is on another server, create the target
connection with something like
`postgresql://user:password@db.example.com:5432/appdb`. If the target database
runs on the host machine while QueryWise runs in Docker, use
`host.docker.internal` as described in [configuration.md](configuration.md).

> **Docker note:** the auto-created IFRS 9 connection is stored as
> `postgresql://sample:sample_dev@sample-db:5432/sampledb`, which is reachable
> from inside the Docker Compose network. If you launch `querywise-mcp` directly
> on your host, it can read the QueryWise metadata DB on `localhost:5432`, but it
> cannot reach the saved target connection host `sample-db`. For the sample DB,
> use HTTP or run stdio inside the `backend` container.

## Claude Code (CLI) and Codex CLI

HTTP works out of the box:

```bash
claude mcp add --transport http querywise http://localhost:8000/mcp
codex mcp add querywise --url http://localhost:8000/mcp
```

Or stdio if you prefer a subprocess:

```bash
claude mcp add querywise -- querywise-mcp
```

For the Docker stack with the bundled IFRS 9 sample DB, spawn stdio inside the
running backend container instead:

```bash
claude mcp add querywise -- docker compose -f /path/to/querywise/docker-compose.yml exec -T backend querywise-mcp
```

## Claude Desktop

Claude Desktop's custom connectors require HTTPS, so stdio is the simplest path. Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (or use Settings → Developer → Edit Config) and add:

```json
{
  "mcpServers": {
    "querywise": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "/path/to/querywise/docker-compose.yml",
        "exec",
        "-T",
        "backend",
        "querywise-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. If you'd rather use the HTTP transport, expose the backend via `ngrok http 8000` and paste the HTTPS URL into **Settings → Connectors → Add custom connector**.

If you are not using Docker, install the CLI locally and point `DATABASE_URL` at
the QueryWise metadata database. Any target connections you create must also use
hostnames reachable from the host process:

```json
{
  "mcpServers": {
    "querywise": {
      "command": "querywise-mcp",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise"
      }
    }
  }
}
```

For example, if you want a host-launched stdio server to query the Docker sample
DB, create or update that target connection with
`postgresql://sample:sample_dev@localhost:5433/sampledb`. An existing auto-seeded
Docker connection that uses `sample-db:5432` will continue to be container-only.

## Cursor / Windsurf

Add to `.cursor/mcp.json` (project) or the global config:

```json
{
  "mcpServers": {
    "querywise": { "url": "http://localhost:8000/mcp" }
  }
}
```

## GitHub Copilot (VS Code)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "querywise": { "type": "http", "url": "http://localhost:8000/mcp" }
  }
}
```

## Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.querywise]
url = "http://localhost:8000/mcp"
```

For Docker-backed stdio in Codex:

```toml
[mcp_servers.querywise]
command = "docker"
args = ["compose", "-f", "/path/to/querywise/docker-compose.yml", "exec", "-T", "backend", "querywise-mcp"]
```

## Installing the `querywise-mcp` CLI

Available after `pip install -e ./backend` (or any wheel built from this repo). Verify with:

```bash
querywise-mcp --help        # or just `querywise-mcp` to start the stdio loop
```

Example uses, once connected:

- *"Add a metric `gross_revenue` on the IFRS 9 connection with expression `SUM(exposure_amount)`."*
- *"Ask the IFRS 9 connection: What is the total ECL by stage?"*

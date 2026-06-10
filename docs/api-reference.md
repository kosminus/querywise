# API Reference

All endpoints are under `/api/v1`. Interactive Swagger docs are served at
`http://localhost:8000/docs` when the backend is running.

## Connections

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/connections` | List all connections |
| `POST` | `/connections` | Create connection |
| `GET` | `/connections/{id}` | Get connection |
| `PUT` | `/connections/{id}` | Update connection |
| `DELETE` | `/connections/{id}` | Delete connection |
| `POST` | `/connections/{id}/test` | Test connection |
| `POST` | `/connections/{id}/introspect` | Introspect schema |

## Schema

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/connections/{id}/tables` | List tables |
| `GET` | `/tables/{table_id}` | Table detail (columns, relationships) |

## Semantic Layer

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/connections/{id}/glossary` | List/create glossary terms |
| `GET/PUT/DELETE` | `/connections/{id}/glossary/{term_id}` | Get/update/delete term |
| `GET/POST` | `/connections/{id}/metrics` | List/create metrics |
| `GET/PUT/DELETE` | `/connections/{id}/metrics/{metric_id}` | Get/update/delete metric |
| `GET/POST` | `/columns/{col_id}/dictionary` | List/create dictionary entries |
| `PUT/DELETE` | `/columns/{col_id}/dictionary/{entry_id}` | Update/delete entry |
| `GET/POST` | `/connections/{id}/knowledge` | List/create knowledge documents |
| `GET/DELETE` | `/connections/{id}/knowledge/{doc_id}` | Get/delete knowledge document |
| `POST` | `/knowledge/fetch-url` | Fetch URL and return parsed content |
| `GET/POST` | `/connections/{id}/sample-queries` | List/create sample queries |
| `PUT/DELETE` | `/connections/{id}/sample-queries/{sq_id}` | Update/delete sample query |

## Query

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Execute NL query (full pipeline) |
| `POST` | `/query/sql-only` | Generate SQL without executing |

## Saved Queries

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/connections/{id}/saved-queries` | List/create saved queries |
| `GET/PUT/DELETE` | `/connections/{id}/saved-queries/{sq_id}` | Get/update/delete saved query |
| `POST` | `/connections/{id}/saved-queries/{sq_id}/run` | Run (cache-first; `refresh` to bypass) |
| `POST` | `/connections/{id}/saved-queries/{sq_id}/clone` | Clone a saved query |
| `GET` | `/connections/{id}/saved-queries/{sq_id}/export` | Export results (`format=csv\|json\|xlsx`) |
| `GET/POST` | `/connections/{id}/saved-queries/{sq_id}/charts` | List/create charts |
| `PUT/DELETE` | `/connections/{id}/saved-queries/{sq_id}/charts/{chart_id}` | Update/delete chart |

## Dashboards

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/dashboards` | List/create dashboards (workspace-scoped) |
| `GET/PUT/DELETE` | `/dashboards/{id}` | Get/update/delete dashboard |
| `POST` | `/dashboards/{id}/tiles` | Add a tile |
| `PUT/DELETE` | `/dashboards/{id}/tiles/{tile_id}` | Update/delete a tile |
| `PUT` | `/dashboards/{id}/layout` | Bulk-save tile positions |
| `POST` | `/dashboards/{id}/tiles/{tile_id}/run` | Run a tile with dashboard filters |

## History

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/query-history` | List query history |
| `GET` | `/query-history/{id}` | Get single execution |
| `PATCH` | `/query-history/{id}/favorite` | Toggle favorite |

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/live` | Liveness probe (process) |
| `GET` | `/health/ready` | Readiness probe (DB + job queue + LLM provider) |

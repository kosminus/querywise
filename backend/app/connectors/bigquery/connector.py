import asyncio
import json
import time
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

from app.connectors.base_connector import (
    BaseConnector,
    ColumnInfo,
    ConnectorType,
    QueryResult,
    TableInfo,
)
from app.core.exceptions import ConnectionError, QueryTimeoutError, SQLSafetyError
from app.utils.sql_sanitizer import check_sql_safety


class BigQueryConnector(BaseConnector):
    connector_type = ConnectorType.BIGQUERY

    def __init__(self) -> None:
        self._client: bigquery.Client | None = None
        self._project_id: str | None = None

    async def connect(self, connection_string: str, **kwargs: Any) -> None:
        try:
            config = json.loads(connection_string)
        except json.JSONDecodeError as e:
            raise ConnectionError(
                "Invalid BigQuery config JSON. Expected "
                '{"project_id": "...", "credentials_json": {...}}'
            ) from e

        project_id = config.get("project_id")
        credentials_json = config.get("credentials_json")

        if not project_id:
            raise ConnectionError("Missing 'project_id' in BigQuery config")
        if not credentials_json:
            raise ConnectionError("Missing 'credentials_json' in BigQuery config")

        try:
            credentials = service_account.Credentials.from_service_account_info(
                credentials_json,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            client = await asyncio.to_thread(
                bigquery.Client, project=project_id, credentials=credentials
            )
            self._client = client
            self._project_id = project_id
        except Exception as e:
            raise ConnectionError(f"BigQuery connection failed: {e}") from e

    async def disconnect(self) -> None:
        if self._client:
            await asyncio.to_thread(self._client.close)
            self._client = None
            self._project_id = None

    async def test_connection(self) -> bool:
        if not self._client:
            return False
        try:
            job = await asyncio.to_thread(self._client.query, "SELECT 1")
            await asyncio.to_thread(job.result)
            return True
        except Exception:
            return False

    async def introspect_schemas(self) -> list[str]:
        assert self._client is not None
        datasets = await asyncio.to_thread(list, self._client.list_datasets())
        return sorted(ds.dataset_id for ds in datasets)

    async def introspect_tables(self, schema: str = "public") -> list[TableInfo]:
        assert self._client is not None
        client = self._client
        project = self._project_id

        # Get tables and views from INFORMATION_SCHEMA
        tables_sql = f"""
            SELECT table_name, table_type
            FROM `{project}.{schema}.INFORMATION_SCHEMA.TABLES`
            ORDER BY table_name
        """
        tables_job = await asyncio.to_thread(client.query, tables_sql)
        table_rows = await asyncio.to_thread(list, tables_job.result())

        # Get all columns in one query
        columns_sql = f"""
            SELECT
                table_name,
                column_name,
                data_type,
                is_nullable,
                ordinal_position
            FROM `{project}.{schema}.INFORMATION_SCHEMA.COLUMNS`
            ORDER BY table_name, ordinal_position
        """
        cols_job = await asyncio.to_thread(client.query, columns_sql)
        col_rows = await asyncio.to_thread(list, cols_job.result())

        # Group columns by table
        columns_by_table: dict[str, list[ColumnInfo]] = {}
        for cr in col_rows:
            tname = cr.table_name
            if tname not in columns_by_table:
                columns_by_table[tname] = []
            columns_by_table[tname].append(
                ColumnInfo(
                    name=cr.column_name,
                    data_type=cr.data_type,
                    is_nullable=cr.is_nullable == "YES",
                    is_primary_key=False,  # BigQuery has no enforced PKs
                    default_value=None,
                    comment=None,  # BigQuery column descriptions require separate API
                    ordinal_position=cr.ordinal_position,
                )
            )

        tables: list[TableInfo] = []
        for trow in table_rows:
            table_name = trow.table_name
            bq_type = trow.table_type
            table_type = "view" if bq_type == "VIEW" else "table"

            # Get row count from table metadata
            row_count: int | None = None
            try:
                table_ref = f"{project}.{schema}.{table_name}"
                table_meta = await asyncio.to_thread(client.get_table, table_ref)
                row_count = table_meta.num_rows
            except Exception:
                pass

            # Get table description from metadata
            comment: str | None = None
            try:
                if table_meta and table_meta.description:
                    comment = table_meta.description
            except Exception:
                pass

            tables.append(
                TableInfo(
                    schema_name=schema,
                    table_name=table_name,
                    table_type=table_type,
                    comment=comment,
                    columns=columns_by_table.get(table_name, []),
                    foreign_keys=[],  # BigQuery has no enforced FK constraints
                    row_count_estimate=row_count,
                )
            )

        return tables

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ) -> QueryResult:
        issues = check_sql_safety(sql)
        if issues:
            raise SQLSafetyError("; ".join(issues))

        assert self._client is not None

        # Wrap with LIMIT if not already present
        wrapped_sql = sql.rstrip().rstrip(";")
        if "limit" not in wrapped_sql.lower():
            wrapped_sql = f"SELECT * FROM ({wrapped_sql}) AS _q LIMIT {max_rows + 1}"

        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
        )

        start = time.monotonic()
        try:
            job = await asyncio.to_thread(
                self._client.query, wrapped_sql, job_config=job_config
            )
            rows = await asyncio.to_thread(
                list, job.result(timeout=timeout_seconds)
            )
        except TimeoutError as e:
            raise QueryTimeoutError(timeout_seconds) from e
        except Exception as e:
            if "timeout" in str(e).lower():
                raise QueryTimeoutError(timeout_seconds) from e
            raise

        elapsed_ms = (time.monotonic() - start) * 1000
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        # Job stats for cost attribution (bytes scanned / billed, slot time).
        job_stats = {
            "scanned_bytes": getattr(job, "total_bytes_processed", None),
            "billed_bytes": getattr(job, "total_bytes_billed", None),
            "slot_ms": getattr(job, "slot_millis", None),
        }
        job_stats = {k: v for k, v in job_stats.items() if v is not None}

        if not rows:
            return QueryResult(
                columns=[],
                column_types=[],
                rows=[],
                stats=job_stats,
                row_count=0,
                execution_time_ms=elapsed_ms,
                truncated=False,
            )

        columns = list(rows[0].keys())
        # Get types from the schema field of the job
        schema_fields = {f.name: f.field_type for f in job.schema or []}
        column_types = [schema_fields.get(col, "STRING") for col in columns]

        result_rows = [list(dict(row).values()) for row in rows]

        return QueryResult(
            columns=columns,
            column_types=column_types,
            rows=result_rows,
            row_count=len(result_rows),
            execution_time_ms=elapsed_ms,
            truncated=truncated,
            stats=job_stats,
        )

    async def get_sample_values(
        self, schema: str, table: str, column: str, limit: int = 20
    ) -> list[Any]:
        assert self._client is not None
        # BigQuery uses backtick quoting for identifiers
        query = f"""
            SELECT DISTINCT `{column}`
            FROM `{self._project_id}.{schema}.{table}`
            WHERE `{column}` IS NOT NULL
            ORDER BY `{column}`
            LIMIT {limit}
        """
        job = await asyncio.to_thread(self._client.query, query)
        rows = await asyncio.to_thread(list, job.result())
        return [row[column] for row in rows]

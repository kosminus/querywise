import asyncio
import json
import time
from typing import Any

from databricks import sql as databricks_sql

from app.connectors.base_connector import (
    BaseConnector,
    ColumnInfo,
    ConnectorType,
    ForeignKeyInfo,
    QueryResult,
    TableInfo,
)
from app.core.exceptions import ConnectionError, QueryTimeoutError, SQLSafetyError
from app.utils.sql_sanitizer import check_sql_safety


class DatabricksConnector(BaseConnector):
    connector_type = ConnectorType.DATABRICKS

    def __init__(self) -> None:
        self._connection: Any | None = None
        self._server_hostname: str | None = None
        self._http_path: str | None = None
        self._catalog: str | None = None

    async def connect(self, connection_string: str, **kwargs: Any) -> None:
        try:
            config = json.loads(connection_string)
        except json.JSONDecodeError as e:
            raise ConnectionError(
                "Invalid Databricks config JSON. Expected "
                '{"server_hostname": "...", "http_path": "...", '
                '"access_token": "...", "catalog": "..."}'
            ) from e

        server_hostname = config.get("server_hostname")
        http_path = config.get("http_path")
        access_token = config.get("access_token")
        catalog = config.get("catalog", "main")

        if not server_hostname:
            raise ConnectionError("Missing 'server_hostname' in Databricks config")
        if not http_path:
            raise ConnectionError("Missing 'http_path' in Databricks config")
        if not access_token:
            raise ConnectionError("Missing 'access_token' in Databricks config")

        try:
            conn = await asyncio.to_thread(
                databricks_sql.connect,
                server_hostname=server_hostname,
                http_path=http_path,
                access_token=access_token,
                catalog=catalog,
            )
            self._connection = conn
            self._server_hostname = server_hostname
            self._http_path = http_path
            self._catalog = catalog
        except Exception as e:
            raise ConnectionError(f"Databricks connection failed: {e}") from e

    async def disconnect(self) -> None:
        if self._connection:
            await asyncio.to_thread(self._connection.close)
            self._connection = None

    async def test_connection(self) -> bool:
        if not self._connection:
            return False
        try:

            def _test() -> bool:
                cursor = self._connection.cursor()
                try:
                    cursor.execute("SELECT 1")
                    cursor.fetchall()
                    return True
                finally:
                    cursor.close()

            return await asyncio.to_thread(_test)
        except Exception:
            return False

    async def introspect_schemas(self) -> list[str]:
        assert self._connection is not None
        catalog = self._catalog

        def _get_schemas() -> list[str]:
            cursor = self._connection.cursor()
            try:
                # SHOW SCHEMAS works on both Unity Catalog and Hive metastore
                cursor.execute(f"SHOW SCHEMAS IN `{catalog}`")
                rows = cursor.fetchall()
                return sorted(row[0] for row in rows)
            finally:
                cursor.close()

        return await asyncio.to_thread(_get_schemas)

    async def introspect_tables(self, schema: str = "public") -> list[TableInfo]:
        assert self._connection is not None
        catalog = self._catalog

        def _introspect() -> list[TableInfo]:
            cursor = self._connection.cursor()
            try:
                return self._introspect_uc(cursor, catalog, schema)
            except Exception:
                # Fall back to Hive metastore commands
                return self._introspect_hive(cursor, catalog, schema)
            finally:
                cursor.close()

        return await asyncio.to_thread(_introspect)

    def _introspect_uc(
        self, cursor: Any, catalog: str, schema: str
    ) -> list[TableInfo]:
        """Introspect using Unity Catalog INFORMATION_SCHEMA (3-part names)."""
        # UC INFORMATION_SCHEMA lives at catalog.information_schema
        cursor.execute(
            f"SELECT table_name, table_type "
            f"FROM `{catalog}`.`information_schema`.`tables` "
            f"WHERE table_schema = '{schema}' "
            f"ORDER BY table_name"
        )
        table_rows = cursor.fetchall()

        cursor.execute(
            f"SELECT table_name, column_name, data_type, "
            f"is_nullable, ordinal_position, column_default, comment "
            f"FROM `{catalog}`.`information_schema`.`columns` "
            f"WHERE table_schema = '{schema}' "
            f"ORDER BY table_name, ordinal_position"
        )
        col_rows = cursor.fetchall()

        # PK constraints (UC only)
        pk_columns: dict[str, set[str]] = {}
        try:
            cursor.execute(
                f"SELECT tc.table_name, kcu.column_name "
                f"FROM `{catalog}`.`information_schema`.`table_constraints` tc "
                f"JOIN `{catalog}`.`information_schema`.`key_column_usage` kcu "
                f"ON tc.constraint_name = kcu.constraint_name "
                f"AND tc.table_schema = kcu.table_schema "
                f"WHERE tc.constraint_type = 'PRIMARY KEY' "
                f"AND tc.table_schema = '{schema}'"
            )
            for row in cursor.fetchall():
                pk_columns.setdefault(row[0], set()).add(row[1])
        except Exception:
            pass

        # FK constraints (UC only)
        fk_map: dict[str, list[ForeignKeyInfo]] = {}
        try:
            cursor.execute(
                f"SELECT "
                f"rc.constraint_name, "
                f"kcu.table_name, kcu.column_name, "
                f"ccu.table_schema, ccu.table_name, ccu.column_name "
                f"FROM `{catalog}`.`information_schema`"
                f".`referential_constraints` rc "
                f"JOIN `{catalog}`.`information_schema`"
                f".`key_column_usage` kcu "
                f"ON rc.constraint_name = kcu.constraint_name "
                f"AND rc.constraint_schema = kcu.table_schema "
                f"JOIN `{catalog}`.`information_schema`"
                f".`constraint_column_usage` ccu "
                f"ON rc.unique_constraint_name = ccu.constraint_name "
                f"AND rc.unique_constraint_schema = ccu.table_schema "
                f"WHERE rc.constraint_schema = '{schema}'"
            )
            for row in cursor.fetchall():
                fk = ForeignKeyInfo(
                    constraint_name=row[0],
                    column_name=row[2],
                    referred_schema=row[3],
                    referred_table=row[4],
                    referred_column=row[5],
                )
                fk_map.setdefault(row[1], []).append(fk)
        except Exception:
            pass

        return self._build_tables(
            cursor, catalog, schema, table_rows, col_rows, pk_columns, fk_map
        )

    def _introspect_hive(
        self, cursor: Any, catalog: str, schema: str
    ) -> list[TableInfo]:
        """Introspect using SHOW/DESCRIBE commands (Hive metastore)."""
        cursor.execute(f"SHOW TABLES IN `{catalog}`.`{schema}`")
        show_rows = cursor.fetchall()

        # SHOW TABLES returns (database, tableName, isTemporary)
        table_names = [row[1] for row in show_rows]

        tables: list[TableInfo] = []
        for table_name in sorted(table_names):
            fqn = f"`{catalog}`.`{schema}`.`{table_name}`"

            # Get columns via DESCRIBE TABLE
            columns: list[ColumnInfo] = []
            comment: str | None = None
            table_type = "table"
            try:
                cursor.execute(f"DESCRIBE TABLE EXTENDED {fqn}")
                desc_rows = cursor.fetchall()
                pos = 1
                in_metadata = False
                for drow in desc_rows:
                    col_name = (drow[0] or "").strip()
                    col_type = (drow[1] or "").strip()
                    col_comment = drow[2] if len(drow) > 2 else None

                    if col_name == "" and col_type == "":
                        in_metadata = True
                        continue
                    if col_name.startswith("#"):
                        continue

                    if in_metadata:
                        if col_name.lower() == "comment":
                            comment = col_type or None
                        elif col_name.lower() == "type":
                            if "VIEW" in (col_type or "").upper():
                                table_type = "view"
                    elif col_name and col_type:
                        columns.append(
                            ColumnInfo(
                                name=col_name,
                                data_type=col_type,
                                is_nullable=True,
                                is_primary_key=False,
                                default_value=None,
                                comment=col_comment.strip()
                                if col_comment and col_comment.strip()
                                else None,
                                ordinal_position=pos,
                            )
                        )
                        pos += 1
            except Exception:
                continue

            # Row count estimate via DESCRIBE DETAIL (Delta tables only)
            row_count: int | None = None
            try:
                cursor.execute(f"DESCRIBE DETAIL {fqn}")
                detail = cursor.fetchone()
                if detail:
                    desc = [d[0] for d in cursor.description]
                    if "numRecords" in desc:
                        row_count = detail[desc.index("numRecords")]
            except Exception:
                pass

            tables.append(
                TableInfo(
                    schema_name=schema,
                    table_name=table_name,
                    table_type=table_type,
                    comment=comment,
                    columns=columns,
                    foreign_keys=[],
                    row_count_estimate=row_count,
                )
            )

        return tables

    def _build_tables(
        self,
        cursor: Any,
        catalog: str,
        schema: str,
        table_rows: list[Any],
        col_rows: list[Any],
        pk_columns: dict[str, set[str]],
        fk_map: dict[str, list[ForeignKeyInfo]],
    ) -> list[TableInfo]:
        """Build TableInfo list from INFORMATION_SCHEMA results."""
        columns_by_table: dict[str, list[ColumnInfo]] = {}
        for cr in col_rows:
            tname = cr[0]
            col_name = cr[1]
            table_pks = pk_columns.get(tname, set())
            if tname not in columns_by_table:
                columns_by_table[tname] = []
            columns_by_table[tname].append(
                ColumnInfo(
                    name=col_name,
                    data_type=cr[2],
                    is_nullable=cr[3] == "YES",
                    is_primary_key=col_name in table_pks,
                    default_value=cr[5],
                    comment=cr[6],
                    ordinal_position=cr[4],
                )
            )

        tables: list[TableInfo] = []
        for trow in table_rows:
            table_name = trow[0]
            ttype = trow[1]
            table_type = "view" if "VIEW" in ttype else "table"
            fqn = f"`{catalog}`.`{schema}`.`{table_name}`"

            # Row count estimate
            row_count: int | None = None
            try:
                cursor.execute(f"DESCRIBE DETAIL {fqn}")
                detail = cursor.fetchone()
                if detail:
                    desc = [d[0] for d in cursor.description]
                    if "numRecords" in desc:
                        row_count = detail[desc.index("numRecords")]
            except Exception:
                pass

            # Table comment
            comment: str | None = None
            try:
                cursor.execute(f"DESCRIBE TABLE EXTENDED {fqn}")
                for drow in cursor.fetchall():
                    if drow[0] and drow[0].strip().lower() == "comment":
                        comment = drow[1]
                        break
            except Exception:
                pass

            tables.append(
                TableInfo(
                    schema_name=schema,
                    table_name=table_name,
                    table_type=table_type,
                    comment=comment,
                    columns=columns_by_table.get(table_name, []),
                    foreign_keys=fk_map.get(table_name, []),
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

        assert self._connection is not None

        # Wrap with LIMIT if not already present
        wrapped_sql = sql.rstrip().rstrip(";")
        if "limit" not in wrapped_sql.lower():
            wrapped_sql = (
                f"SELECT * FROM ({wrapped_sql}) AS _q LIMIT {max_rows + 1}"
            )

        def _execute() -> QueryResult:
            start = time.monotonic()
            cursor = self._connection.cursor()
            try:
                cursor.execute(wrapped_sql)
                rows = cursor.fetchall()
                elapsed_ms = (time.monotonic() - start) * 1000

                truncated = len(rows) > max_rows
                rows = rows[:max_rows]

                if not rows:
                    return QueryResult(
                        columns=[],
                        column_types=[],
                        rows=[],
                        row_count=0,
                        execution_time_ms=elapsed_ms,
                        truncated=False,
                    )

                columns = [desc[0] for desc in cursor.description]
                column_types = [
                    desc[1] or "STRING" for desc in cursor.description
                ]
                result_rows = [list(row) for row in rows]

                return QueryResult(
                    columns=columns,
                    column_types=column_types,
                    rows=result_rows,
                    row_count=len(result_rows),
                    execution_time_ms=elapsed_ms,
                    truncated=truncated,
                )
            finally:
                cursor.close()

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_execute),
                timeout=timeout_seconds,
            )
        except TimeoutError as e:
            raise QueryTimeoutError(timeout_seconds) from e
        except Exception as e:
            if "timeout" in str(e).lower():
                raise QueryTimeoutError(timeout_seconds) from e
            raise

    async def get_sample_values(
        self, schema: str, table: str, column: str, limit: int = 20
    ) -> list[Any]:
        assert self._connection is not None
        catalog = self._catalog

        def _sample() -> list[Any]:
            cursor = self._connection.cursor()
            try:
                cursor.execute(
                    f"SELECT DISTINCT `{column}` "
                    f"FROM `{catalog}`.`{schema}`.`{table}` "
                    f"WHERE `{column}` IS NOT NULL "
                    f"ORDER BY `{column}` "
                    f"LIMIT {limit}"
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()

        return await asyncio.to_thread(_sample)

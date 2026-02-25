from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConnectorType(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    DATABRICKS = "databricks"


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    default_value: str | None
    comment: str | None
    ordinal_position: int


@dataclass
class ForeignKeyInfo:
    constraint_name: str
    column_name: str
    referred_schema: str
    referred_table: str
    referred_column: str


@dataclass
class TableInfo:
    schema_name: str
    table_name: str
    table_type: str  # "table" | "view"
    comment: str | None
    columns: list[ColumnInfo] = field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)
    row_count_estimate: int | None = None


@dataclass
class QueryResult:
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool


class BaseConnector(ABC):
    """Abstract interface for database connectors.

    All implementations must enforce read-only query execution.
    """

    connector_type: ConnectorType

    @abstractmethod
    async def connect(self, connection_string: str, **kwargs: Any) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        ...

    @abstractmethod
    async def introspect_schemas(self) -> list[str]:
        ...

    @abstractmethod
    async def introspect_tables(self, schema: str = "public") -> list[TableInfo]:
        ...

    @abstractmethod
    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ) -> QueryResult:
        ...

    @abstractmethod
    async def get_sample_values(
        self, schema: str, table: str, column: str, limit: int = 20
    ) -> list[Any]:
        ...

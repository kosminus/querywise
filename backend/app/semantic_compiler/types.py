"""Dataclasses and protocols shared across the compiler. No app imports."""

from dataclasses import dataclass, field
from typing import Any, Protocol


class Prober(Protocol):
    """Narrow read-only database access used by collectors and probes.

    The in-app implementation adapts ``BaseConnector``; a standalone CLI can
    implement it directly over asyncpg.
    """

    async def query(self, sql: str, max_rows: int = 1000) -> list[dict[str, Any]]: ...

    async def sample_values(
        self, schema: str, table: str, column: str, limit: int = 20
    ) -> list[Any]: ...


@dataclass
class DeclaredFK:
    source_column: str
    target_schema: str
    target_table: str
    target_column: str


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    comment: str | None = None
    ordinal_position: int = 0
    # pg_stats enrichment (None = stats unavailable)
    null_frac: float | None = None
    n_distinct: float | None = None
    most_common_vals: list[str] | None = None
    most_common_freqs: list[float] | None = None
    # constraint/index enrichment
    is_unique: bool = False
    check_in_values: list[str] | None = None
    enum_values: list[str] | None = None
    # sampled values (PII detection)
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class TableProfile:
    schema_name: str
    table_name: str
    table_type: str = "table"  # "table" | "view"
    comment: str | None = None
    row_count_estimate: int | None = None
    columns: list[ColumnProfile] = field(default_factory=list)
    declared_fks: list[DeclaredFK] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"

    def column(self, name: str) -> ColumnProfile | None:
        for col in self.columns:
            if col.name == name:
                return col
        return None


@dataclass
class ViewDef:
    schema_name: str
    view_name: str
    sql: str


@dataclass
class LoggedQuery:
    sql: str
    calls: int = 1
    total_time_ms: float = 0.0


@dataclass
class Evidence:
    source: str  # naming | value_overlap | query_logs | pg_stats | view | constraint | heuristic
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "detail": self.detail}


# Finding kinds
KIND_RELATIONSHIP = "relationship"
KIND_METRIC = "metric"
KIND_DICTIONARY = "dictionary"
KIND_GLOSSARY = "glossary"
KIND_ROW_FILTER = "data_policy_row_filter"
KIND_MASKING = "data_policy_masking"
KIND_DEAD_TABLE = "dead_table"
KIND_FANOUT = "fanout_warning"

ALL_KINDS = (
    KIND_RELATIONSHIP,
    KIND_METRIC,
    KIND_DICTIONARY,
    KIND_GLOSSARY,
    KIND_ROW_FILTER,
    KIND_MASKING,
    KIND_DEAD_TABLE,
    KIND_FANOUT,
)


@dataclass
class Finding:
    kind: str
    title: str
    payload: dict[str, Any]
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0


def _default_caps() -> dict[str, int]:
    # Review fatigue kills draft-generation tools: cap output hard.
    return {
        KIND_RELATIONSHIP: 40,
        KIND_METRIC: 30,
        KIND_DICTIONARY: 60,
        KIND_GLOSSARY: 15,
        KIND_ROW_FILTER: 3,
        KIND_MASKING: 25,
        KIND_DEAD_TABLE: 20,
        KIND_FANOUT: 20,
    }


@dataclass
class Thresholds:
    min_confidence: float = 0.5
    max_per_kind: dict[str, int] = field(default_factory=_default_caps)
    # Value-overlap probes are real queries against the target DB — budget them.
    probe_budget: int = 60
    probe_sample_rows: int = 500


@dataclass
class CompilerInput:
    dialect: str | None = None  # sqlglot dialect, e.g. "postgres"
    tables: list[TableProfile] = field(default_factory=list)
    views: list[ViewDef] = field(default_factory=list)
    logged_queries: list[LoggedQuery] = field(default_factory=list)
    # Which evidence sources actually answered (for run stats / UI messaging).
    sources_available: dict[str, bool] = field(default_factory=dict)
    # ignore_declared_fks: treat declared FKs as absent (eval mode)
    options: dict[str, Any] = field(default_factory=dict)

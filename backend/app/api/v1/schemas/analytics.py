from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_queries: int
    error_count: int
    error_rate: float
    total_cost_usd: float
    total_scanned_bytes: int
    avg_execution_ms: float | None


class CostByEntry(BaseModel):
    key: str | None
    cost_usd: float
    query_count: int


class SlowestQuery(BaseModel):
    query_execution_id: str | None
    execution_time_ms: float | None
    cost_usd: float
    source_provider: str | None
    question: str | None


class TableUsage(BaseModel):
    table: str
    query_count: int

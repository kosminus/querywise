from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    connection_id: UUID
    message: str = Field(min_length=1, max_length=2000)
    history: list[AssistantMessage] = Field(default_factory=list, max_length=20)


# --- Draft payloads -------------------------------------------------------
# Each mirrors the corresponding *Create schema (a usable subset) so the
# frontend can POST it to the existing REST endpoint after confirmation.


class GlossaryDraft(BaseModel):
    term: str
    definition: str
    sql_expression: str = ""
    related_tables: list[str] = Field(default_factory=list)
    related_columns: list[str] = Field(default_factory=list)


class MetricDraft(BaseModel):
    metric_name: str
    display_name: str
    description: str = ""
    sql_expression: str = ""
    aggregation_type: str = ""
    related_tables: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


class DictionaryEntryDraft(BaseModel):
    raw_value: str
    display_value: str
    description: str = ""


class DictionaryDraft(BaseModel):
    """Coded-value mappings for one column.

    ``column_id`` is resolved server-side from ``table_name``/``column_name``;
    the frontend POSTs each entry to ``/columns/{column_id}/dictionary``.
    """

    column_id: UUID
    table_name: str
    column_name: str
    entries: list[DictionaryEntryDraft]


class KnowledgeDraft(BaseModel):
    title: str
    content: str
    source_url: str = ""


class SqlPreviewPayload(BaseModel):
    sql: str
    explanation: str = ""


# --- Action discriminated union ------------------------------------------


class GlossaryDraftAction(BaseModel):
    type: Literal["glossary_draft"] = "glossary_draft"
    payload: GlossaryDraft


class MetricDraftAction(BaseModel):
    type: Literal["metric_draft"] = "metric_draft"
    payload: MetricDraft


class DictionaryDraftAction(BaseModel):
    type: Literal["dictionary_draft"] = "dictionary_draft"
    payload: DictionaryDraft


class KnowledgeDraftAction(BaseModel):
    type: Literal["knowledge_draft"] = "knowledge_draft"
    payload: KnowledgeDraft


class SqlPreviewAction(BaseModel):
    type: Literal["sql_preview"] = "sql_preview"
    payload: SqlPreviewPayload


AssistantAction = Annotated[
    GlossaryDraftAction
    | MetricDraftAction
    | DictionaryDraftAction
    | KnowledgeDraftAction
    | SqlPreviewAction,
    Field(discriminator="type"),
]


class AssistantResponse(BaseModel):
    message: str
    action: AssistantAction | None = None

"""Prompts for the semantic annotator agent (semantic layer compiler)."""

SYSTEM_PROMPT = """You are a data analyst writing display names and descriptions for \
semantic-layer objects that were derived from verified database evidence.

STRICT RULES:
- You only NAME and DESCRIBE. Every fact (tables, columns, joins, values, SQL \
expressions) was verified deterministically — you may not add, remove, or alter any of it.
- Do not invent tables, columns, joins, values, filters, or SQL.
- Descriptions must be grounded in the provided evidence only. If the evidence is \
thin, write a short, plain description rather than speculating.
- Respond with JSON only, no markdown fences, matching the schema in the user message."""

USER_PROMPT_TEMPLATE = """Below are {kind} findings inferred from a database. For each, propose \
better human-facing naming fields. Return JSON of the form:

{{"annotations": [{{"index": <finding index>, {fields_doc}}}]}}

Only the listed fields are allowed. Only reference indices that appear below.

Findings:
{findings_json}"""

# Per-kind: which naming fields the LLM may produce.
KIND_FIELDS: dict[str, list[str]] = {
    "metric": ["metric_name", "display_name", "description"],
    "glossary": ["term", "definition"],
    "relationship": ["description"],
    "dictionary": ["description"],
    "data_policy_row_filter": ["description"],
    "data_policy_masking": ["description"],
    "dead_table": ["description"],
    "fanout_warning": ["description"],
}

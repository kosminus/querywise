"""Assembles the LLM prompt from selected semantic context."""

from app.semantic.glossary_resolver import (
    ResolvedDictionary,
    ResolvedGlossary,
    ResolvedKnowledge,
    ResolvedMetric,
    ResolvedSampleQuery,
)
from app.semantic.schema_linker import LinkedTable


def assemble_prompt(
    tables: list[LinkedTable],
    glossary: list[ResolvedGlossary],
    metrics: list[ResolvedMetric],
    knowledge: list[ResolvedKnowledge],
    dictionaries: list[ResolvedDictionary],
    sample_queries: list[ResolvedSampleQuery],
    relationships: list[dict],
    dialect: str = "postgresql",
) -> str:
    """Format all selected context into a structured prompt section for the LLM."""
    sections: list[str] = []

    # Schema section
    if tables:
        schema_lines = ["=== DATABASE SCHEMA ==="]
        for lt in tables:
            table = lt.table
            schema_lines.append(f"\nTable: {table.schema_name}.{table.table_name}")
            if table.comment:
                schema_lines.append(f"  Description: {table.comment}")
            if table.row_count_estimate:
                schema_lines.append(f"  Approximate rows: {table.row_count_estimate:,}")

            for col in lt.columns:
                parts = [f"  - {col.column_name} ({col.data_type}"]
                if col.is_primary_key:
                    parts.append(", PK")
                if not col.is_nullable:
                    parts.append(", NOT NULL")
                parts.append(")")
                if col.comment:
                    parts.append(f" -- {col.comment}")
                schema_lines.append("".join(parts))

        sections.append("\n".join(schema_lines))

    # Relationships section
    if relationships:
        rel_lines = ["\n=== RELATIONSHIPS ==="]
        for rel in relationships:
            rel_lines.append(
                f"  {rel['source_table']}.{rel['source_column']} -> "
                f"{rel['target_table']}.{rel['target_column']}"
            )
        sections.append("\n".join(rel_lines))

    # Business glossary section
    if glossary:
        glossary_lines = ["\n=== BUSINESS GLOSSARY ==="]
        glossary_lines.append("Use these definitions when the user refers to these terms:")
        for g in glossary:
            glossary_lines.append(f'  - "{g.term}": {g.definition}')
            glossary_lines.append(f"    SQL: {g.sql_expression}")
            if g.related_tables:
                glossary_lines.append(f"    Tables: {', '.join(g.related_tables)}")
        sections.append("\n".join(glossary_lines))

    # Metrics section
    if metrics:
        metric_lines = ["\n=== METRIC DEFINITIONS ==="]
        for m in metrics:
            metric_lines.append(f'  - "{m.display_name}" ({m.metric_name})')
            metric_lines.append(f"    SQL: {m.sql_expression}")
            if m.dimensions:
                metric_lines.append(f"    Suggested dimensions: {', '.join(m.dimensions)}")
        sections.append("\n".join(metric_lines))

    # Business knowledge section
    if knowledge:
        knowledge_lines = ["\n=== BUSINESS KNOWLEDGE ==="]
        knowledge_lines.append(
            "Relevant documentation excerpts:"
        )
        for k in knowledge:
            source = k.title
            if k.source_url:
                source += f" ({k.source_url})"
            knowledge_lines.append(f'  [Source: "{source}"]')
            text = k.content[:500] + "..." if len(k.content) > 500 else k.content
            knowledge_lines.append(f"  {text}")
            knowledge_lines.append("")
        sections.append("\n".join(knowledge_lines))

    # Data dictionary section
    if dictionaries:
        dict_lines = ["\n=== DATA DICTIONARY ==="]
        dict_lines.append("Column value mappings (use these to interpret or filter values):")
        for d in dictionaries:
            mappings = ", ".join(f"{k}={v}" for k, v in d.mappings.items())
            dict_lines.append(f"  - {d.column_name}: {mappings}")
        sections.append("\n".join(dict_lines))

    # Sample queries section (few-shot examples)
    if sample_queries:
        sample_lines = ["\n=== EXAMPLE QUERIES ==="]
        sample_lines.append("Here are some validated query examples for reference:")
        for sq in sample_queries:
            sample_lines.append(f"  Q: {sq.natural_language}")
            sample_lines.append(f"  SQL: {sq.sql_query}")
            sample_lines.append("")
        sections.append("\n".join(sample_lines))

    # Constraints section
    constraint_lines = ["\n=== CONSTRAINTS ==="]
    constraint_lines.append(f"- SQL dialect: {dialect}")
    constraint_lines.append("- Read-only: generate only SELECT statements")
    constraint_lines.append("- Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE")
    constraint_lines.append("- Limit results to 1000 rows unless user specifies otherwise")
    constraint_lines.append("- Use explicit column names, not SELECT *")
    sections.append("\n".join(constraint_lines))

    return "\n".join(sections)

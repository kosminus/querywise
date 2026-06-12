"""Semantic layer compiler.

Introspects an operational database (schema catalog, column statistics, view
definitions, query logs) and produces draft semantic-layer findings — inferred
join paths, dictionary entries, metric candidates, glossary entities, and
refusal boundaries (PII masking, tenant row filters, dead tables, fan-out
warnings) — each carrying evidence and a confidence score for human review.

Design rules:
* Deterministic inference produces all facts; the LLM pass only names and
  describes them (see ``app/llm/agents/semantic_annotator.py``).
* This package is self-contained: dataclasses + pure functions, no FastAPI or
  ORM imports. Database access goes through the narrow ``Prober`` protocol so
  a standalone CLI can be extracted later.
"""

from app.semantic_compiler.engine import run_compiler
from app.semantic_compiler.types import (
    CompilerInput,
    Finding,
    Prober,
    Thresholds,
)

__all__ = ["CompilerInput", "Finding", "Prober", "Thresholds", "run_compiler"]

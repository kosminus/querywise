"""PII detection -> draft masking policy.

Two independent signals: column-name patterns and value-shape regexes over
sampled rows. Both together -> high confidence; name alone -> medium.
"""

import logging
import re
from re import Pattern

from app.semantic_compiler.types import (
    KIND_MASKING,
    Evidence,
    Finding,
    Prober,
    TableProfile,
)

logger = logging.getLogger(__name__)

# category -> column-name pattern
_NAME_PATTERNS: dict[str, Pattern[str]] = {
    "email": re.compile(r"e?mail", re.IGNORECASE),
    "phone": re.compile(r"phone|mobile|fax", re.IGNORECASE),
    "national_id": re.compile(r"ssn|national_id|tax_id|passport|nino", re.IGNORECASE),
    "date_of_birth": re.compile(r"birth|dob", re.IGNORECASE),
    "address": re.compile(r"address|street|postcode|zip_?code", re.IGNORECASE),
    "bank_account": re.compile(r"iban|account_number|routing", re.IGNORECASE),
    "person_name": re.compile(r"^(full|first|last|middle|family|given)_?name$", re.IGNORECASE),
}

# category -> value-shape validator (None = name+type is the only signal)
_VALUE_PATTERNS: dict[str, Pattern[str] | None] = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "phone": re.compile(r"^\+?[\d][\d\s().-]{6,}$"),
    "national_id": re.compile(r"^(\d{7,10}|\d{3}-\d{2}-\d{4})$"),
    "date_of_birth": None,
    "address": None,
    "bank_account": re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$|^\d{8,17}$"),
    "person_name": None,
}

_SAMPLE_BUDGET = 30  # max columns to sample per run


def _categorize(column_name: str) -> str | None:
    for category, pattern in _NAME_PATTERNS.items():
        if pattern.search(column_name):
            return category
    return None


async def infer_pii(tables: list[TableProfile], prober: Prober) -> list[Finding]:
    findings: list[Finding] = []
    samples_left = _SAMPLE_BUDGET

    for table in tables:
        if table.table_type != "table":
            continue
        for col in table.columns:
            category = _categorize(col.name)
            if category is None:
                continue
            if category == "date_of_birth" and "date" not in col.data_type.lower():
                continue

            confidence = 0.55
            evidence = [Evidence("naming", f"column name matches the {category} pattern")]

            validator = _VALUE_PATTERNS.get(category)
            if validator is not None and samples_left > 0:
                samples_left -= 1
                try:
                    values = await prober.sample_values(
                        table.schema_name, table.table_name, col.name, limit=20
                    )
                except Exception as exc:
                    logger.debug(
                        "PII sampling failed for %s.%s: %s", table.table_name, col.name, exc
                    )
                    values = []
                non_null = [str(v) for v in values if v is not None]
                if non_null:
                    matched = sum(1 for v in non_null if validator.match(v.strip()))
                    if matched / len(non_null) >= 0.6:
                        confidence = 0.85
                        evidence.append(
                            Evidence(
                                "value_overlap",
                                f"{matched} of {len(non_null)} sampled values "
                                f"match the {category} shape",
                            )
                        )

            findings.append(
                Finding(
                    kind=KIND_MASKING,
                    title=f"PII candidate: {table.table_name}.{col.name} ({category})",
                    payload={
                        "schema": table.schema_name,
                        "table": table.table_name,
                        "column": col.name,
                        "category": category,
                        "masked_column": f"{table.table_name}.{col.name}",
                    },
                    evidence=evidence,
                    confidence=confidence,
                )
            )
    return findings

"""Agent: Semantic Annotator — names/describes compiler findings.

The semantic layer compiler produces findings deterministically; this agent's
only job is to replace machine-generated names and descriptions with
human-quality ones. Its output is merged onto the findings' *naming fields
only* — it cannot add or alter facts. Annotation is optional: any failure
leaves the deterministic fallback names in place.
"""

import json
import logging
import re

from app.llm.base_provider import BaseLLMProvider, LLMConfig, LLMMessage
from app.llm.prompts.annotator_prompts import KIND_FIELDS, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.llm.utils import repair_json

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_MAX_FIELD_LEN = 2000
_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]+")


def _sanitize_identifier(value: str) -> str:
    cleaned = _IDENTIFIER_RE.sub("_", value.strip().lower()).strip("_")
    return cleaned[:255] or "unnamed"


class SemanticAnnotatorAgent:
    def __init__(self, provider: BaseLLMProvider, config: LLMConfig):
        self.provider = provider
        self.config = config

    async def annotate(self, kind: str, findings: list[dict]) -> dict[int, dict[str, str]]:
        """Return {finding_index: {field: value}} for one kind of finding.

        ``findings`` are dicts with at least ``title``, ``payload``, ``evidence``.
        Per-batch failures are swallowed — callers always get a (possibly
        partial or empty) mapping.
        """
        allowed_fields = KIND_FIELDS.get(kind)
        if not allowed_fields or not findings:
            return {}

        annotations: dict[int, dict[str, str]] = {}
        for start in range(0, len(findings), _BATCH_SIZE):
            batch = findings[start : start + _BATCH_SIZE]
            try:
                annotations.update(
                    await self._annotate_batch(kind, allowed_fields, batch, offset=start)
                )
            except Exception as exc:
                logger.warning("annotation batch failed for kind=%s: %s", kind, exc)
        return annotations

    async def _annotate_batch(
        self, kind: str, allowed_fields: list[str], batch: list[dict], offset: int
    ) -> dict[int, dict[str, str]]:
        findings_json = json.dumps(
            [
                {
                    "index": offset + i,
                    "title": f.get("title"),
                    "payload": f.get("payload"),
                    "evidence": f.get("evidence"),
                }
                for i, f in enumerate(batch)
            ],
            default=str,
            indent=2,
        )
        fields_doc = ", ".join(f'"{name}": "..."' for name in allowed_fields)
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=USER_PROMPT_TEMPLATE.format(
                    kind=kind, fields_doc=fields_doc, findings_json=findings_json
                ),
            ),
        ]
        response = await self.provider.complete(messages, self.config)
        parsed = json.loads(repair_json(response.content))

        valid_indices = {offset + i for i in range(len(batch))}
        result: dict[int, dict[str, str]] = {}
        for item in parsed.get("annotations", []):
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            if index not in valid_indices:
                continue  # the model referenced a finding we didn't send
            fields: dict[str, str] = {}
            for field in allowed_fields:
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    continue
                value = value.strip()[:_MAX_FIELD_LEN]
                if field == "metric_name":
                    value = _sanitize_identifier(value)
                fields[field] = value
            if fields:
                result[index] = fields
        return result

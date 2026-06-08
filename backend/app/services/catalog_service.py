"""Catalog search service (Phase 3 — Milestone 2).

A unified, read-side discovery layer over the schema cache + semantic layer.
Reuses the existing pgvector embeddings and the keyword scorer from the NL→SQL
pipeline (``relevance_scorer``) — no new full-text infrastructure. Results across
tables, columns, metrics, glossary terms, sample queries, saved queries, and
knowledge documents are merged into a uniform :class:`CatalogHit`, with certified
items boosted in the ranking.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.glossary import GlossaryTerm
from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.models.metric import MetricDefinition
from app.db.models.sample_query import SampleQuery
from app.db.models.saved_query import SavedQuery
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.semantic.relevance_scorer import extract_keywords, keyword_match_score
from app.services.embedding_service import embed_text

logger = logging.getLogger(__name__)

# Hit types.
TYPE_TABLE = "table"
TYPE_COLUMN = "column"
TYPE_METRIC = "metric"
TYPE_GLOSSARY = "glossary"
TYPE_SAMPLE_QUERY = "sample_query"
TYPE_SAVED_QUERY = "saved_query"
TYPE_KNOWLEDGE = "knowledge"
ALL_TYPES = (
    TYPE_TABLE,
    TYPE_COLUMN,
    TYPE_METRIC,
    TYPE_GLOSSARY,
    TYPE_SAMPLE_QUERY,
    TYPE_SAVED_QUERY,
    TYPE_KNOWLEDGE,
)

_W_EMB = 0.6
_W_KW = 0.4
_CERT_BOOST = 0.15
_VECTOR_LIMIT = 20


@dataclass
class CatalogHit:
    type: str
    id: str
    name: str
    description: str | None = None
    status: str | None = None
    certified_at: datetime | None = None
    owner_id: str | None = None
    context: str | None = None  # e.g. "schema.table" for a column, schema for a table
    score: float = 0.0
    match_reason: str = "keyword"


def _combine(emb: float, kw: float, status: str | None) -> tuple[float, str]:
    score = _W_EMB * emb + _W_KW * kw
    if status == "certified":
        score += _CERT_BOOST
    return score, ("embedding" if emb >= kw else "keyword")


async def _vector_hits(db: AsyncSession, stmt) -> list:
    """Execute a pgvector similarity query, degrading to [] on failure (e.g. dim mismatch)."""
    try:
        result = await db.execute(stmt)
        return list(result.all())
    except Exception:
        logger.warning("Catalog vector search failed; keyword-only for this type.", exc_info=True)
        await db.rollback()
        return []


async def search(
    db: AsyncSession,
    connection_id: uuid.UUID,
    query: str,
    *,
    types: list[str] | None = None,
    status: str | None = None,
    owner: str | None = None,
    schema: str | None = None,
    limit: int = 50,
) -> list[CatalogHit]:
    """Hybrid search across the schema cache + semantic layer for one connection."""
    wanted = set(types) if types else set(ALL_TYPES)
    keywords = extract_keywords(query) if query else []

    qvec: list[float] | None = None
    if query.strip():
        try:
            qvec = await embed_text(query)
        except Exception:
            logger.debug("Catalog query embedding failed; keyword-only.", exc_info=True)

    hits: list[CatalogHit] = []

    if TYPE_TABLE in wanted:
        hits += await _search_tables(db, connection_id, qvec, keywords, schema)
    if TYPE_COLUMN in wanted:
        hits += await _search_columns(db, connection_id, qvec, keywords, schema)
    if TYPE_GLOSSARY in wanted:
        hits += await _search_glossary(db, connection_id, qvec, keywords)
    if TYPE_METRIC in wanted:
        hits += await _search_metrics(db, connection_id, qvec, keywords)
    if TYPE_SAMPLE_QUERY in wanted:
        hits += await _search_sample_queries(db, connection_id, qvec, keywords)
    if TYPE_SAVED_QUERY in wanted:
        hits += await _search_saved_queries(db, connection_id, keywords)
    if TYPE_KNOWLEDGE in wanted:
        hits += await _search_knowledge(db, connection_id, qvec, keywords)

    # Facet filters applied post-merge (status/owner only meaningful for some types).
    if status:
        hits = [h for h in hits if h.status == status]
    if owner:
        hits = [h for h in hits if h.owner_id == owner]

    return rank_hits(hits, limit)


def rank_hits(hits: list[CatalogHit], limit: int) -> list[CatalogHit]:
    """Order hits certified-first, then by score; truncate to ``limit``."""
    hits.sort(key=lambda h: (h.status == "certified", h.score), reverse=True)
    return hits[:limit]


# --------------------------------------------------------------------------- #
# Per-type searches
# --------------------------------------------------------------------------- #
async def _search_tables(db, connection_id, qvec, keywords, schema) -> list[CatalogHit]:
    scores: dict[uuid.UUID, tuple[float, float]] = {}  # id -> (emb, kw)
    rows: dict[uuid.UUID, CachedTable] = {}

    if qvec is not None:
        stmt = (
            select(
                CachedTable,
                (1 - CachedTable.description_embedding.cosine_distance(qvec)).label("sim"),
            )
            .where(
                CachedTable.connection_id == connection_id,
                CachedTable.description_embedding.isnot(None),
            )
            .order_by(CachedTable.description_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for tbl, sim in await _vector_hits(db, stmt):
            rows[tbl.id] = tbl
            scores[tbl.id] = (float(sim), 0.0)

    if keywords:
        conds = [CachedTable.table_name.ilike(f"%{kw}%") for kw in keywords]
        result = await db.execute(
            select(CachedTable).where(CachedTable.connection_id == connection_id, or_(*conds))
        )
        for tbl in result.scalars().all():
            rows[tbl.id] = tbl
            emb = scores.get(tbl.id, (0.0, 0.0))[0]
            scores[tbl.id] = (emb, keyword_match_score(tbl.table_name, keywords))

    hits = []
    for tid, tbl in rows.items():
        if schema and tbl.schema_name != schema:
            continue
        emb, kw = scores[tid]
        score, reason = _combine(emb, kw, None)
        hits.append(
            CatalogHit(
                type=TYPE_TABLE,
                id=str(tbl.id),
                name=tbl.table_name,
                description=tbl.comment,
                context=tbl.schema_name,
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_columns(db, connection_id, qvec, keywords, schema) -> list[CatalogHit]:
    scores: dict[uuid.UUID, tuple[float, float]] = {}
    rows: dict[uuid.UUID, tuple[CachedColumn, CachedTable]] = {}

    if qvec is not None:
        stmt = (
            select(
                CachedColumn,
                CachedTable,
                (1 - CachedColumn.description_embedding.cosine_distance(qvec)).label("sim"),
            )
            .join(CachedTable, CachedColumn.table_id == CachedTable.id)
            .where(
                CachedTable.connection_id == connection_id,
                CachedColumn.description_embedding.isnot(None),
            )
            .order_by(CachedColumn.description_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for col, tbl, sim in await _vector_hits(db, stmt):
            rows[col.id] = (col, tbl)
            scores[col.id] = (float(sim), 0.0)

    if keywords:
        conds = [CachedColumn.column_name.ilike(f"%{kw}%") for kw in keywords]
        result = await db.execute(
            select(CachedColumn, CachedTable)
            .join(CachedTable, CachedColumn.table_id == CachedTable.id)
            .where(CachedTable.connection_id == connection_id, or_(*conds))
            .limit(100)
        )
        for col, tbl in result.all():
            rows[col.id] = (col, tbl)
            emb = scores.get(col.id, (0.0, 0.0))[0]
            scores[col.id] = (emb, keyword_match_score(col.column_name, keywords))

    hits = []
    for cid, (col, tbl) in rows.items():
        if schema and tbl.schema_name != schema:
            continue
        emb, kw = scores[cid]
        score, reason = _combine(emb, kw, None)
        hits.append(
            CatalogHit(
                type=TYPE_COLUMN,
                id=str(col.id),
                name=col.column_name,
                description=col.comment,
                context=f"{tbl.schema_name}.{tbl.table_name}",
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_glossary(db, connection_id, qvec, keywords) -> list[CatalogHit]:
    scores: dict[uuid.UUID, tuple[float, float]] = {}
    rows: dict[uuid.UUID, GlossaryTerm] = {}

    if qvec is not None:
        stmt = (
            select(
                GlossaryTerm,
                (1 - GlossaryTerm.term_embedding.cosine_distance(qvec)).label("sim"),
            )
            .where(
                GlossaryTerm.connection_id == connection_id,
                GlossaryTerm.term_embedding.isnot(None),
            )
            .order_by(GlossaryTerm.term_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for term, sim in await _vector_hits(db, stmt):
            rows[term.id] = term
            scores[term.id] = (float(sim), 0.0)

    if keywords:
        conds = [GlossaryTerm.term.ilike(f"%{kw}%") for kw in keywords]
        result = await db.execute(
            select(GlossaryTerm).where(GlossaryTerm.connection_id == connection_id, or_(*conds))
        )
        for term in result.scalars().all():
            rows[term.id] = term
            emb = scores.get(term.id, (0.0, 0.0))[0]
            scores[term.id] = (emb, keyword_match_score(term.term, keywords))

    hits = []
    for tid, term in rows.items():
        emb, kw = scores[tid]
        score, reason = _combine(emb, kw, term.status)
        hits.append(
            CatalogHit(
                type=TYPE_GLOSSARY,
                id=str(term.id),
                name=term.term,
                description=term.definition,
                status=term.status,
                certified_at=term.certified_at,
                owner_id=str(term.created_by_id) if term.created_by_id else None,
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_metrics(db, connection_id, qvec, keywords) -> list[CatalogHit]:
    scores: dict[uuid.UUID, tuple[float, float]] = {}
    rows: dict[uuid.UUID, MetricDefinition] = {}

    if qvec is not None:
        stmt = (
            select(
                MetricDefinition,
                (1 - MetricDefinition.metric_embedding.cosine_distance(qvec)).label("sim"),
            )
            .where(
                MetricDefinition.connection_id == connection_id,
                MetricDefinition.metric_embedding.isnot(None),
            )
            .order_by(MetricDefinition.metric_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for metric, sim in await _vector_hits(db, stmt):
            rows[metric.id] = metric
            scores[metric.id] = (float(sim), 0.0)

    if keywords:
        conds = [MetricDefinition.metric_name.ilike(f"%{kw}%") for kw in keywords] + [
            MetricDefinition.display_name.ilike(f"%{kw}%") for kw in keywords
        ]
        result = await db.execute(
            select(MetricDefinition).where(
                MetricDefinition.connection_id == connection_id, or_(*conds)
            )
        )
        for metric in result.scalars().all():
            rows[metric.id] = metric
            emb = scores.get(metric.id, (0.0, 0.0))[0]
            kw = max(
                keyword_match_score(metric.metric_name, keywords),
                keyword_match_score(metric.display_name, keywords),
            )
            scores[metric.id] = (emb, kw)

    hits = []
    for mid, metric in rows.items():
        emb, kw = scores[mid]
        score, reason = _combine(emb, kw, metric.status)
        hits.append(
            CatalogHit(
                type=TYPE_METRIC,
                id=str(metric.id),
                name=metric.display_name or metric.metric_name,
                description=metric.description,
                status=metric.status,
                certified_at=metric.certified_at,
                owner_id=str(metric.created_by_id) if metric.created_by_id else None,
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_sample_queries(db, connection_id, qvec, keywords) -> list[CatalogHit]:
    scores: dict[uuid.UUID, tuple[float, float]] = {}
    rows: dict[uuid.UUID, SampleQuery] = {}

    if qvec is not None:
        stmt = (
            select(
                SampleQuery,
                (1 - SampleQuery.question_embedding.cosine_distance(qvec)).label("sim"),
            )
            .where(
                SampleQuery.connection_id == connection_id,
                SampleQuery.question_embedding.isnot(None),
            )
            .order_by(SampleQuery.question_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for sq, sim in await _vector_hits(db, stmt):
            rows[sq.id] = sq
            scores[sq.id] = (float(sim), 0.0)

    if keywords:
        conds = [SampleQuery.natural_language.ilike(f"%{kw}%") for kw in keywords]
        result = await db.execute(
            select(SampleQuery).where(SampleQuery.connection_id == connection_id, or_(*conds))
        )
        for sq in result.scalars().all():
            rows[sq.id] = sq
            emb = scores.get(sq.id, (0.0, 0.0))[0]
            scores[sq.id] = (emb, keyword_match_score(sq.natural_language, keywords))

    hits = []
    for sid, sq in rows.items():
        emb, kw = scores[sid]
        score, reason = _combine(emb, kw, sq.status)
        hits.append(
            CatalogHit(
                type=TYPE_SAMPLE_QUERY,
                id=str(sq.id),
                name=sq.natural_language[:120],
                description=sq.description,
                status=sq.status,
                certified_at=sq.certified_at,
                owner_id=str(sq.created_by_id) if sq.created_by_id else None,
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_saved_queries(db, connection_id, keywords) -> list[CatalogHit]:
    # No embedding column on saved queries — keyword-only.
    if not keywords:
        return []
    conds = [SavedQuery.name.ilike(f"%{kw}%") for kw in keywords]
    result = await db.execute(
        select(SavedQuery).where(SavedQuery.connection_id == connection_id, or_(*conds))
    )
    hits = []
    for sq in result.scalars().all():
        kw = keyword_match_score(sq.name, keywords)
        score, reason = _combine(0.0, kw, sq.status)
        hits.append(
            CatalogHit(
                type=TYPE_SAVED_QUERY,
                id=str(sq.id),
                name=sq.name,
                description=sq.description,
                status=sq.status,
                certified_at=sq.certified_at,
                owner_id=str(sq.owner_id) if sq.owner_id else None,
                score=score,
                match_reason=reason,
            )
        )
    return hits


async def _search_knowledge(db, connection_id, qvec, keywords) -> list[CatalogHit]:
    # Search chunks by vector, collapse to the best score per document.
    best: dict[uuid.UUID, float] = {}
    docs: dict[uuid.UUID, KnowledgeDocument] = {}

    if qvec is not None:
        stmt = (
            select(
                KnowledgeDocument,
                (1 - KnowledgeChunk.chunk_embedding.cosine_distance(qvec)).label("sim"),
            )
            .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.connection_id == connection_id,
                KnowledgeChunk.chunk_embedding.isnot(None),
            )
            .order_by(KnowledgeChunk.chunk_embedding.cosine_distance(qvec))
            .limit(_VECTOR_LIMIT)
        )
        for doc, sim in await _vector_hits(db, stmt):
            docs[doc.id] = doc
            best[doc.id] = max(best.get(doc.id, 0.0), float(sim))

    if keywords:
        conds = [KnowledgeDocument.title.ilike(f"%{kw}%") for kw in keywords]
        result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.connection_id == connection_id, or_(*conds)
            )
        )
        for doc in result.scalars().all():
            docs[doc.id] = doc

    hits = []
    for did, doc in docs.items():
        emb = best.get(did, 0.0)
        kw = keyword_match_score(doc.title, keywords) if keywords else 0.0
        score, reason = _combine(emb, kw, None)
        hits.append(
            CatalogHit(
                type=TYPE_KNOWLEDGE,
                id=str(doc.id),
                name=doc.title,
                description=doc.source_url,
                score=score,
                match_reason=reason,
            )
        )
    return hits


# --------------------------------------------------------------------------- #
# Facets
# --------------------------------------------------------------------------- #
async def facets(db: AsyncSession, connection_id: uuid.UUID) -> dict:
    """Return available facet values for the filter sidebar."""
    schemas = list(
        (
            await db.execute(
                select(CachedTable.schema_name)
                .where(CachedTable.connection_id == connection_id)
                .distinct()
                .order_by(CachedTable.schema_name)
            )
        )
        .scalars()
        .all()
    )

    owners: set[str] = set()
    for model, col in (
        (MetricDefinition, MetricDefinition.created_by_id),
        (GlossaryTerm, GlossaryTerm.created_by_id),
        (SampleQuery, SampleQuery.created_by_id),
        (SavedQuery, SavedQuery.owner_id),
    ):
        result = await db.execute(
            select(col).where(model.connection_id == connection_id, col.isnot(None)).distinct()
        )
        owners.update(str(v) for v in result.scalars().all())

    # Status counts across the lifecycle entities.
    status_counts: dict[str, int] = {}
    for model in (MetricDefinition, GlossaryTerm, SampleQuery, SavedQuery):
        result = await db.execute(
            select(model.status, func.count())
            .where(model.connection_id == connection_id)
            .group_by(model.status)
        )
        for st, cnt in result.all():
            status_counts[st] = status_counts.get(st, 0) + cnt

    # Tags from sample queries (ARRAY column).
    tags: set[str] = set()
    tag_rows = await db.execute(
        select(SampleQuery.tags).where(
            SampleQuery.connection_id == connection_id, SampleQuery.tags.isnot(None)
        )
    )
    for tag_list in tag_rows.scalars().all():
        for tag in tag_list or []:
            tags.add(str(tag))

    return {
        "schemas": schemas,
        "owners": sorted(owners),
        "tags": sorted(tags),
        "types": list(ALL_TYPES),
        "status_counts": status_counts,
    }

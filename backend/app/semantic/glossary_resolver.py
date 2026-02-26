"""Resolves business glossary terms and metrics from a NL question."""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.db.models.dictionary import DictionaryEntry
from app.db.models.glossary import GlossaryTerm
from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.models.metric import MetricDefinition
from app.db.models.sample_query import SampleQuery
from app.db.models.schema_cache import CachedColumn
from app.semantic.relevance_scorer import extract_keywords


@dataclass
class ResolvedGlossary:
    term: str
    definition: str
    sql_expression: str
    related_tables: list[str]


@dataclass
class ResolvedMetric:
    metric_name: str
    display_name: str
    sql_expression: str
    related_tables: list[str]
    dimensions: list[str]


@dataclass
class ResolvedDictionary:
    table_name: str
    column_name: str
    mappings: dict[str, str]  # raw_value -> display_value


@dataclass
class ResolvedKnowledge:
    title: str
    source_url: str | None
    content: str


@dataclass
class ResolvedSampleQuery:
    natural_language: str
    sql_query: str


async def resolve_glossary(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
    question_embedding: list[float] | None = None,
) -> list[ResolvedGlossary]:
    """Find glossary terms relevant to the question.

    Uses keyword matching + optional embedding similarity.
    """
    keywords = extract_keywords(question)
    results: list[ResolvedGlossary] = []
    seen_terms: set[str] = set()

    # Keyword matching against term names
    all_terms_result = await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.connection_id == connection_id)
    )
    all_terms = all_terms_result.scalars().all()

    for term in all_terms:
        term_lower = term.term.lower()
        for kw in keywords:
            if kw in term_lower or term_lower in kw:
                if term.term not in seen_terms:
                    results.append(ResolvedGlossary(
                        term=term.term,
                        definition=term.definition,
                        sql_expression=term.sql_expression,
                        related_tables=term.related_tables or [],
                    ))
                    seen_terms.add(term.term)
                break

    # Also check question text directly for term matches
    question_lower = question.lower()
    for term in all_terms:
        if term.term.lower() in question_lower and term.term not in seen_terms:
            results.append(ResolvedGlossary(
                term=term.term,
                definition=term.definition,
                sql_expression=term.sql_expression,
                related_tables=term.related_tables or [],
            ))
            seen_terms.add(term.term)

    # Embedding similarity (top 3)
    if question_embedding:
        try:
            stmt = (
                select(GlossaryTerm)
                .where(
                    GlossaryTerm.connection_id == connection_id,
                    GlossaryTerm.term_embedding.isnot(None),
                )
                .order_by(GlossaryTerm.term_embedding.cosine_distance(question_embedding))
                .limit(3)
            )
            emb_result = await db.execute(stmt)
            for term in emb_result.scalars().all():
                if term.term not in seen_terms:
                    results.append(ResolvedGlossary(
                        term=term.term,
                        definition=term.definition,
                        sql_expression=term.sql_expression,
                        related_tables=term.related_tables or [],
                    ))
                    seen_terms.add(term.term)
        except Exception:
            logger.warning("Glossary vector search failed, using keyword results only.", exc_info=True)

    return results


async def resolve_metrics(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
    question_embedding: list[float] | None = None,
) -> list[ResolvedMetric]:
    """Find metric definitions relevant to the question."""
    results: list[ResolvedMetric] = []
    seen: set[str] = set()

    question_lower = question.lower()

    all_metrics_result = await db.execute(
        select(MetricDefinition).where(MetricDefinition.connection_id == connection_id)
    )
    for metric in all_metrics_result.scalars().all():
        if metric.display_name.lower() in question_lower or metric.metric_name.lower() in question_lower:
            if metric.metric_name not in seen:
                results.append(ResolvedMetric(
                    metric_name=metric.metric_name,
                    display_name=metric.display_name,
                    sql_expression=metric.sql_expression,
                    related_tables=metric.related_tables or [],
                    dimensions=metric.dimensions or [],
                ))
                seen.add(metric.metric_name)

    # Embedding similarity
    if question_embedding:
        try:
            stmt = (
                select(MetricDefinition)
                .where(
                    MetricDefinition.connection_id == connection_id,
                    MetricDefinition.metric_embedding.isnot(None),
                )
                .order_by(
                    MetricDefinition.metric_embedding.cosine_distance(question_embedding)
                )
                .limit(3)
            )
            emb_result = await db.execute(stmt)
            for metric in emb_result.scalars().all():
                if metric.metric_name not in seen:
                    results.append(ResolvedMetric(
                        metric_name=metric.metric_name,
                        display_name=metric.display_name,
                        sql_expression=metric.sql_expression,
                        related_tables=metric.related_tables or [],
                        dimensions=metric.dimensions or [],
                    ))
                    seen.add(metric.metric_name)
        except Exception:
            logger.warning("Metrics vector search failed, using keyword results only.", exc_info=True)

    return results


async def resolve_dictionary(
    db: AsyncSession,
    column_ids: list[uuid.UUID],
) -> list[ResolvedDictionary]:
    """Get data dictionary entries for the given columns."""
    if not column_ids:
        return []

    result = await db.execute(
        select(DictionaryEntry, CachedColumn)
        .join(CachedColumn, DictionaryEntry.column_id == CachedColumn.id)
        .where(DictionaryEntry.column_id.in_(column_ids))
        .order_by(DictionaryEntry.sort_order)
    )

    # Group by column
    grouped: dict[uuid.UUID, ResolvedDictionary] = {}
    for entry, column in result.all():
        if column.id not in grouped:
            grouped[column.id] = ResolvedDictionary(
                table_name="",  # Will be filled
                column_name=column.column_name,
                mappings={},
            )
        grouped[column.id].mappings[entry.raw_value] = entry.display_value

    return list(grouped.values())


async def find_similar_queries(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question_embedding: list[float] | None,
    limit: int = 3,
) -> list[ResolvedSampleQuery]:
    """Find the most similar validated sample queries."""
    if question_embedding is None:
        return []

    try:
        stmt = (
            select(SampleQuery)
            .where(
                SampleQuery.connection_id == connection_id,
                SampleQuery.is_validated.is_(True),
                SampleQuery.question_embedding.isnot(None),
            )
            .order_by(SampleQuery.question_embedding.cosine_distance(question_embedding))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            ResolvedSampleQuery(
                natural_language=sq.natural_language,
                sql_query=sq.sql_query,
            )
            for sq in result.scalars().all()
        ]
    except Exception:
        logger.warning("Sample query vector search failed.", exc_info=True)
        return []


async def resolve_knowledge(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
    question_embedding: list[float] | None,
    limit: int = 5,
) -> list[ResolvedKnowledge]:
    """Find the most relevant knowledge chunks.

    Uses vector similarity when embeddings are available, falls back to
    keyword ILIKE search otherwise (or when vector search fails).
    """
    if question_embedding is not None:
        try:
            stmt = (
                select(KnowledgeChunk, KnowledgeDocument)
                .join(
                    KnowledgeDocument,
                    KnowledgeChunk.document_id == KnowledgeDocument.id,
                )
                .where(
                    KnowledgeDocument.connection_id == connection_id,
                    KnowledgeChunk.chunk_embedding.isnot(None),
                )
                .order_by(
                    KnowledgeChunk.chunk_embedding.cosine_distance(
                        question_embedding
                    )
                )
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.all()
            if rows:
                return [
                    ResolvedKnowledge(
                        title=doc.title,
                        source_url=doc.source_url,
                        content=chunk.content,
                    )
                    for chunk, doc in rows
                ]
        except Exception:
            logger.warning(
                "Knowledge vector search failed, using keyword fallback.",
                exc_info=True,
            )

    # Keyword fallback
    keywords = [kw for kw in extract_keywords(question) if len(kw) > 2][:8]
    if not keywords:
        return []

    keyword_predicates = [
        KnowledgeChunk.content.ilike(f"%{kw}%") for kw in keywords
    ]
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(
            KnowledgeDocument,
            KnowledgeChunk.document_id == KnowledgeDocument.id,
        )
        .where(
            KnowledgeDocument.connection_id == connection_id,
            or_(*keyword_predicates),
        )
        .order_by(KnowledgeChunk.chunk_index.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        ResolvedKnowledge(
            title=doc.title,
            source_url=doc.source_url,
            content=chunk.content,
        )
        for chunk, doc in result.all()
    ]

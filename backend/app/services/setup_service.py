"""
Auto-setup service for the IFRS 9 sample database.

On startup, this service:
1. Ensures vector column dimensions match EMBEDDING_DIMENSION setting
2. Creates a connection to the sample DB (if not already present)
3. Introspects the schema (if not already done)
4. Seeds glossary terms, metrics, and dictionary entries (if empty)

All operations are idempotent — safe to run on every restart.
"""

import asyncio
import logging
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models.connection import DatabaseConnection
from app.db.models.dictionary import DictionaryEntry
from app.db.models.glossary import GlossaryTerm
from app.db.models.knowledge import KnowledgeDocument
from app.db.models.metric import MetricDefinition
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.db.session import async_session_factory
from app.services import connection_service, schema_service

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Vector dimension check — runs on every startup
# ---------------------------------------------------------------------------
EMBEDDING_COLUMNS = [
    ("cached_tables", "description_embedding"),
    ("cached_columns", "description_embedding"),
    ("glossary_terms", "term_embedding"),
    ("metric_definitions", "metric_embedding"),
    ("sample_queries", "question_embedding"),
    ("knowledge_chunks", "chunk_embedding"),
]


async def ensure_embedding_dimensions() -> None:
    """Check if vector columns match EMBEDDING_DIMENSION and resize if needed.

    Alembic migration 002 only runs once. If the user switches providers
    (e.g. OpenAI 1536 → Ollama 768) after the migration has already run,
    the columns keep the old dimension. This function detects the mismatch
    and fixes it at startup — nulling stale embeddings so they regenerate.
    """
    target_dim = settings.embedding_dimension

    async with async_session_factory() as db:
        # Check the first embedding column's dimension as a proxy for all
        result = await db.execute(text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'cached_tables'::regclass "
            "AND attname = 'description_embedding'"
        ))
        row = result.scalar_one_or_none()

        if row is None:
            # Column doesn't exist yet (first run before migrations)
            return

        current_dim = row  # pgvector stores dimension in atttypmod
        if current_dim == target_dim:
            return

        logger.info(
            "Embedding dimension mismatch: DB has %d, config wants %d. "
            "Resizing columns and clearing stale embeddings...",
            current_dim, target_dim,
        )
        for table, column in EMBEDDING_COLUMNS:
            await db.execute(text(
                f"UPDATE {table} SET {column} = NULL "
                f"WHERE {column} IS NOT NULL"
            ))
            await db.execute(text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN {column} TYPE vector({target_dim}) "
                f"USING {column}::vector({target_dim})"
            ))
        await db.commit()
        logger.info(
            "Embedding columns resized to %d dimensions. "
            "Embeddings will regenerate in the background.",
            target_dim,
        )


CONNECTION_NAME = "IFRS 9 Sample DB"

# ---------------------------------------------------------------------------
# Glossary terms
# ---------------------------------------------------------------------------
GLOSSARY_TERMS = [
    {
        "term": "EAD",
        "definition": (
            "Exposure at Default - the total amount a bank is exposed to at the time "
            "of a borrower's default. This is the gross carrying amount for on-balance sheet items."
        ),
        "sql_expression": "exposures.ead",
        "related_tables": ["exposures"],
        "related_columns": ["exposures.ead"],
        "examples": ["SELECT SUM(ead) FROM exposures WHERE reporting_date = '2024-12-31'"],
    },
    {
        "term": "PD",
        "definition": (
            "Probability of Default - the likelihood that a borrower will default on their "
            "obligations within a given time horizon (12 months for Stage 1, lifetime for Stage 2/3)."
        ),
        "sql_expression": "ecl_provisions.pd",
        "related_tables": ["ecl_provisions"],
        "related_columns": ["ecl_provisions.pd"],
        "examples": ["SELECT AVG(pd) FROM ecl_provisions WHERE stage = 1"],
    },
    {
        "term": "LGD",
        "definition": (
            "Loss Given Default - the percentage of exposure that is lost if a borrower defaults, "
            "after accounting for recoveries and collateral."
        ),
        "sql_expression": "ecl_provisions.lgd",
        "related_tables": ["ecl_provisions", "collateral"],
        "related_columns": ["ecl_provisions.lgd"],
        "examples": ["SELECT AVG(lgd) FROM ecl_provisions WHERE stage = 3"],
    },
    {
        "term": "ECL",
        "definition": (
            "Expected Credit Loss - the probability-weighted estimate of credit losses. "
            "Calculated as PD x LGD x EAD. Under IFRS 9, Stage 1 uses 12-month ECL "
            "while Stage 2 and 3 use lifetime ECL."
        ),
        "sql_expression": "ecl_provisions.ecl_lifetime",
        "related_tables": ["ecl_provisions", "exposures"],
        "related_columns": ["ecl_provisions.ecl_12m", "ecl_provisions.ecl_lifetime"],
        "examples": [
            "SELECT SUM(ecl_lifetime) FROM ecl_provisions",
            "SELECT stage, SUM(ecl_lifetime) FROM ecl_provisions GROUP BY stage",
        ],
    },
    {
        "term": "Stage 1",
        "definition": (
            "Performing loans with no significant increase in credit risk since origination. "
            "Only 12-month ECL is recognised as a provision."
        ),
        "sql_expression": "exposures.stage = 1",
        "related_tables": ["exposures", "ecl_provisions"],
        "related_columns": ["exposures.stage"],
        "examples": ["SELECT * FROM exposures WHERE stage = 1"],
    },
    {
        "term": "Stage 2",
        "definition": (
            "Loans with a Significant Increase in Credit Risk (SICR) since origination "
            "but not yet credit-impaired. Lifetime ECL is recognised."
        ),
        "sql_expression": "exposures.stage = 2",
        "related_tables": ["exposures", "ecl_provisions", "staging_history"],
        "related_columns": ["exposures.stage"],
        "examples": ["SELECT * FROM exposures WHERE stage = 2"],
    },
    {
        "term": "Stage 3",
        "definition": (
            "Credit-impaired (defaulted) loans. Lifetime ECL is recognised and "
            "interest revenue is calculated on the net carrying amount."
        ),
        "sql_expression": "exposures.stage = 3",
        "related_tables": ["exposures", "ecl_provisions"],
        "related_columns": ["exposures.stage"],
        "examples": ["SELECT * FROM exposures WHERE stage = 3"],
    },
    {
        "term": "SICR",
        "definition": (
            "Significant Increase in Credit Risk - the trigger for moving a loan from "
            "Stage 1 to Stage 2 under IFRS 9. Assessed using quantitative and qualitative criteria."
        ),
        "sql_expression": "staging_history.to_stage = 2",
        "related_tables": ["staging_history", "exposures"],
        "related_columns": ["staging_history.to_stage", "staging_history.reason"],
        "examples": ["SELECT * FROM staging_history WHERE to_stage = 2 AND reason = 'downgrade'"],
    },
    {
        "term": "Coverage Ratio",
        "definition": (
            "The ratio of ECL provisions to total exposure (EAD). Indicates the level of "
            "provisioning relative to the outstanding loan book."
        ),
        "sql_expression": "SUM(ecl_provisions.ecl_lifetime) / SUM(exposures.ead)",
        "related_tables": ["ecl_provisions", "exposures"],
        "related_columns": ["ecl_provisions.ecl_lifetime", "exposures.ead"],
        "examples": [],
    },
    {
        "term": "NPL",
        "definition": (
            "Non-Performing Loan - loans classified as Stage 3 (credit-impaired) under IFRS 9. "
            "These are loans where the borrower has defaulted or is unlikely to pay."
        ),
        "sql_expression": "exposures.stage = 3",
        "related_tables": ["exposures", "counterparties"],
        "related_columns": ["exposures.stage", "counterparties.is_defaulted"],
        "examples": [
            "SELECT COUNT(*) FROM exposures WHERE stage = 3",
            "SELECT SUM(ead) FROM exposures WHERE stage = 3",
        ],
    },
]

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
METRICS = [
    {
        "metric_name": "total_ecl",
        "display_name": "Total ECL",
        "description": "Total Expected Credit Loss across the entire portfolio",
        "sql_expression": "SUM(ecl_provisions.ecl_lifetime)",
        "aggregation_type": "sum",
        "related_tables": ["ecl_provisions"],
        "dimensions": ["stage", "facility_type", "segment", "currency"],
    },
    {
        "metric_name": "total_ead",
        "display_name": "Total EAD",
        "description": "Total Exposure at Default across the entire portfolio",
        "sql_expression": "SUM(exposures.ead)",
        "aggregation_type": "sum",
        "related_tables": ["exposures"],
        "dimensions": ["stage", "facility_type", "segment", "currency"],
    },
    {
        "metric_name": "coverage_ratio",
        "display_name": "Coverage Ratio",
        "description": "ECL as a percentage of total EAD — indicates provisioning adequacy",
        "sql_expression": "SUM(ecl_provisions.ecl_lifetime) / NULLIF(SUM(exposures.ead), 0)",
        "aggregation_type": "ratio",
        "related_tables": ["ecl_provisions", "exposures"],
        "dimensions": ["stage", "facility_type", "segment"],
    },
    {
        "metric_name": "stage1_exposure",
        "display_name": "Stage 1 Exposure",
        "description": "Total EAD for performing loans (Stage 1 — 12-month ECL)",
        "sql_expression": "SUM(exposures.ead) FILTER (WHERE exposures.stage = 1)",
        "aggregation_type": "sum",
        "related_tables": ["exposures"],
        "dimensions": ["facility_type", "segment", "currency"],
        "filters": {"stage": 1},
    },
    {
        "metric_name": "stage2_exposure",
        "display_name": "Stage 2 Exposure",
        "description": "Total EAD for SICR loans (Stage 2 — lifetime ECL)",
        "sql_expression": "SUM(exposures.ead) FILTER (WHERE exposures.stage = 2)",
        "aggregation_type": "sum",
        "related_tables": ["exposures"],
        "dimensions": ["facility_type", "segment", "currency"],
        "filters": {"stage": 2},
    },
    {
        "metric_name": "stage3_exposure",
        "display_name": "Stage 3 Exposure",
        "description": "Total EAD for credit-impaired loans (Stage 3 — lifetime ECL)",
        "sql_expression": "SUM(exposures.ead) FILTER (WHERE exposures.stage = 3)",
        "aggregation_type": "sum",
        "related_tables": ["exposures"],
        "dimensions": ["facility_type", "segment", "currency"],
        "filters": {"stage": 3},
    },
    {
        "metric_name": "average_pd",
        "display_name": "Average PD",
        "description": "Weighted average Probability of Default across the portfolio",
        "sql_expression": "AVG(ecl_provisions.pd)",
        "aggregation_type": "avg",
        "related_tables": ["ecl_provisions"],
        "dimensions": ["stage", "facility_type", "segment"],
    },
    {
        "metric_name": "npl_ratio",
        "display_name": "NPL Ratio",
        "description": "Non-Performing Loan ratio — Stage 3 EAD as a percentage of total EAD",
        "sql_expression": (
            "SUM(exposures.ead) FILTER (WHERE exposures.stage = 3) "
            "/ NULLIF(SUM(exposures.ead), 0)"
        ),
        "aggregation_type": "ratio",
        "related_tables": ["exposures"],
        "dimensions": ["facility_type", "segment", "currency"],
    },
]

# ---------------------------------------------------------------------------
# Dictionary entries — keyed by (table_name, column_name)
# ---------------------------------------------------------------------------
DICTIONARY_ENTRIES: dict[tuple[str, str], list[dict]] = {
    ("exposures", "stage"): [
        {"raw_value": "1", "display_value": "Stage 1 - Performing", "description": "No significant increase in credit risk; 12-month ECL", "sort_order": 1},
        {"raw_value": "2", "display_value": "Stage 2 - SICR", "description": "Significant increase in credit risk; lifetime ECL", "sort_order": 2},
        {"raw_value": "3", "display_value": "Stage 3 - Credit-Impaired", "description": "Credit-impaired / defaulted; lifetime ECL", "sort_order": 3},
    ],
    ("facilities", "facility_type"): [
        {"raw_value": "mortgage", "display_value": "Mortgage Loan", "description": "Residential or commercial mortgage", "sort_order": 1},
        {"raw_value": "corporate_loan", "display_value": "Corporate Loan", "description": "Term loan to a corporate entity", "sort_order": 2},
        {"raw_value": "consumer_loan", "display_value": "Consumer Loan", "description": "Unsecured personal loan", "sort_order": 3},
        {"raw_value": "credit_card", "display_value": "Credit Card", "description": "Revolving credit card facility", "sort_order": 4},
        {"raw_value": "overdraft", "display_value": "Overdraft", "description": "Overdraft facility on current account", "sort_order": 5},
    ],
    ("counterparties", "segment"): [
        {"raw_value": "retail", "display_value": "Retail Banking", "description": "Individual consumers and households", "sort_order": 1},
        {"raw_value": "corporate", "display_value": "Corporate Banking", "description": "Large corporate entities", "sort_order": 2},
        {"raw_value": "sme", "display_value": "SME Banking", "description": "Small and medium enterprises", "sort_order": 3},
    ],
    ("collateral", "collateral_type"): [
        {"raw_value": "property", "display_value": "Real Estate Property", "description": "Residential or commercial real estate", "sort_order": 1},
        {"raw_value": "cash", "display_value": "Cash Deposit", "description": "Cash held as security", "sort_order": 2},
        {"raw_value": "guarantee", "display_value": "Bank Guarantee", "description": "Third-party bank guarantee", "sort_order": 3},
        {"raw_value": "securities", "display_value": "Securities", "description": "Bonds, equities, or other financial instruments", "sort_order": 4},
    ],
    ("staging_history", "reason"): [
        {"raw_value": "origination", "display_value": "New Origination", "description": "Initial recognition at Stage 1", "sort_order": 1},
        {"raw_value": "upgrade", "display_value": "Credit Improvement", "description": "Upgrade due to improved credit quality", "sort_order": 2},
        {"raw_value": "downgrade", "display_value": "Credit Deterioration", "description": "Downgrade due to SICR or default triggers", "sort_order": 3},
        {"raw_value": "cure", "display_value": "Return to Performing", "description": "Recovery from impaired status", "sort_order": 4},
        {"raw_value": "default", "display_value": "Default Event", "description": "Borrower entered default", "sort_order": 5},
    ],
    ("counterparties", "credit_rating"): [
        {"raw_value": "AAA", "display_value": "AAA - Prime", "description": "Highest credit quality; minimal default risk", "sort_order": 1},
        {"raw_value": "AA", "display_value": "AA - High Grade", "description": "Very high credit quality; very low default risk", "sort_order": 2},
        {"raw_value": "A", "display_value": "A - Upper Medium", "description": "High credit quality; low default risk", "sort_order": 3},
        {"raw_value": "BBB", "display_value": "BBB - Lower Medium", "description": "Good credit quality; moderate default risk (investment grade floor)", "sort_order": 4},
        {"raw_value": "BB", "display_value": "BB - Speculative", "description": "Speculative; substantial credit risk (sub-investment grade)", "sort_order": 5},
        {"raw_value": "B", "display_value": "B - Highly Speculative", "description": "Highly speculative; high default risk", "sort_order": 6},
        {"raw_value": "CCC", "display_value": "CCC - Substantial Risk", "description": "Very high credit risk; near default", "sort_order": 7},
    ],
    ("counterparties", "is_defaulted"): [
        {"raw_value": "true", "display_value": "Defaulted", "description": "Counterparty has defaulted on obligations", "sort_order": 1},
        {"raw_value": "false", "display_value": "Performing", "description": "Counterparty is current on obligations", "sort_order": 2},
    ],
    ("facilities", "currency"): [
        {"raw_value": "EUR", "display_value": "Euro", "description": "European single currency", "sort_order": 1},
        {"raw_value": "USD", "display_value": "US Dollar", "description": "United States dollar", "sort_order": 2},
        {"raw_value": "GBP", "display_value": "British Pound", "description": "British pound sterling", "sort_order": 3},
    ],
    ("facilities", "is_revolving"): [
        {"raw_value": "true", "display_value": "Revolving", "description": "Revolving credit facility (e.g. credit card, overdraft) — can be drawn and repaid repeatedly", "sort_order": 1},
        {"raw_value": "false", "display_value": "Term / Amortising", "description": "Term facility with scheduled repayment (e.g. mortgage, term loan)", "sort_order": 2},
    ],
    ("ecl_provisions", "stage"): [
        {"raw_value": "1", "display_value": "Stage 1 - Performing", "description": "No significant increase in credit risk; 12-month ECL", "sort_order": 1},
        {"raw_value": "2", "display_value": "Stage 2 - SICR", "description": "Significant increase in credit risk; lifetime ECL", "sort_order": 2},
        {"raw_value": "3", "display_value": "Stage 3 - Credit-Impaired", "description": "Credit-impaired / defaulted; lifetime ECL", "sort_order": 3},
    ],
    ("staging_history", "from_stage"): [
        {"raw_value": "1", "display_value": "Stage 1 - Performing", "description": "No significant increase in credit risk", "sort_order": 1},
        {"raw_value": "2", "display_value": "Stage 2 - SICR", "description": "Significant increase in credit risk", "sort_order": 2},
        {"raw_value": "3", "display_value": "Stage 3 - Credit-Impaired", "description": "Credit-impaired / defaulted", "sort_order": 3},
    ],
    ("staging_history", "to_stage"): [
        {"raw_value": "1", "display_value": "Stage 1 - Performing", "description": "No significant increase in credit risk", "sort_order": 1},
        {"raw_value": "2", "display_value": "Stage 2 - SICR", "description": "Significant increase in credit risk", "sort_order": 2},
        {"raw_value": "3", "display_value": "Stage 3 - Credit-Impaired", "description": "Credit-impaired / defaulted", "sort_order": 3},
    ],
}

# ---------------------------------------------------------------------------
# Knowledge document — IFRS 9 staging and ECL rules
# ---------------------------------------------------------------------------
KNOWLEDGE_DOCUMENT = {
    "title": "IFRS 9 Staging & ECL Policy Summary",
    "source_url": "https://internal.wiki/ifrs9-staging-policy",
    "content": """\
IFRS 9 Staging Criteria and ECL Calculation Policy

This document describes the bank's staging criteria under IFRS 9 and the \
corresponding Expected Credit Loss (ECL) calculation methodology.

Stage Classification

All facilities are classified into one of three stages at each reporting date:

Stage 1 — Performing: The facility has not experienced a Significant Increase \
in Credit Risk (SICR) since initial recognition. The bank recognises \
12-month ECL as a provision.

Stage 2 — Underperforming (SICR): The facility has experienced a SICR but is \
not yet credit-impaired. The bank recognises lifetime ECL. SICR triggers \
include: (a) a credit rating downgrade of 2 or more notches since origination, \
(b) the facility being more than 30 days past due, (c) the counterparty being \
placed on a watch list, (d) adverse macro-economic indicators for the \
counterparty's sector.

Stage 3 — Non-Performing (Credit-Impaired): The facility meets the definition \
of default. Default triggers include: (a) more than 90 days past due, \
(b) the counterparty is flagged as defaulted (is_defaulted = true), \
(c) the facility has been restructured due to financial difficulty. \
Lifetime ECL is recognised and interest revenue is calculated on the \
net carrying amount (gross amount minus ECL provision).

ECL Calculation

ECL is calculated as: ECL = PD x LGD x EAD, where:
- PD (Probability of Default): 12-month PD for Stage 1, lifetime PD for \
Stage 2 and 3. PD values are stored in the ecl_provisions table.
- LGD (Loss Given Default): Estimated loss percentage if default occurs, \
taking into account collateral recoveries. Lower LGD values indicate \
better collateral coverage. Stored in ecl_provisions.lgd.
- EAD (Exposure at Default): The gross carrying amount of the facility \
at the reporting date. Stored in exposures.ead.

The ecl_provisions table contains both ecl_12m (12-month ECL, used for \
Stage 1 reporting) and ecl_lifetime (lifetime ECL, used for Stage 2 \
and Stage 3 reporting).

Collateral and LGD

Collateral reduces LGD. Each collateral record is linked to a facility \
and has a collateral_value and haircut percentage. The net collateral \
value (collateral_value * (1 - haircut)) offsets the exposure. \
Collateral types include property, cash deposits, bank guarantees, \
and securities.

Stage Migration

The staging_history table tracks all stage transitions. Each record \
contains the from_stage, to_stage, transition_date, and a reason code. \
Reason codes are: origination (new loan at Stage 1), upgrade (improvement \
in credit quality), downgrade (SICR or deterioration), cure (return to \
performing after impairment), default (borrower entered default). \
A facility moving from Stage 1 to Stage 2 is a "downgrade" due to SICR. \
A facility moving from Stage 3 back to Stage 1 is a "cure".

Reporting Dimensions

The portfolio is typically analysed along these dimensions:
- By stage (1, 2, 3) — the primary risk segmentation
- By segment (retail, corporate, SME) — business unit view
- By facility_type (mortgage, corporate_loan, consumer_loan, credit_card, \
overdraft) — product type view
- By currency (EUR, USD, GBP) — currency exposure view
- By credit_rating (AAA through CCC) — credit quality distribution
- By reporting_date — time series analysis across quarters
""",
}


MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 3


async def auto_setup_sample_db() -> None:
    """Auto-setup the IFRS 9 sample database connection and metadata.

    Retries up to MAX_RETRIES times with a delay, because the sample-db
    container may still be starting (no hard depends_on in docker-compose).
    """
    logger.info("Auto-setup: starting sample DB setup...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with async_session_factory() as db:
                try:
                    connection = await _ensure_connection(db)
                    connection_id = connection.id

                    if connection.last_introspected_at is None:
                        logger.info("Auto-setup: introspecting schema...")
                        await schema_service.introspect_and_cache(db, connection_id)
                        await db.commit()
                        # Refresh to get updated last_introspected_at
                        await db.refresh(connection)
                        logger.info("Auto-setup: schema introspected successfully")
                    else:
                        logger.info("Auto-setup: schema already introspected, skipping")

                    await _seed_glossary(db, connection_id)
                    await _seed_metrics(db, connection_id)
                    await _seed_dictionary(db, connection_id)
                    await _seed_knowledge(db, connection_id)

                    await db.commit()
                    logger.info(
                        "Auto-setup: completed, launching background "
                        "embedding generation"
                    )
                    launch_background_embeddings(connection_id)
                    return
                except Exception:
                    await db.rollback()
                    raise
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.info(
                    "Auto-setup: attempt %d/%d failed (%s), retrying in %ds...",
                    attempt, MAX_RETRIES, e, RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.warning(
                    "Auto-setup: failed after %d attempts (%s: %s) "
                    "— server will start without sample data",
                    MAX_RETRIES, type(e).__name__, e,
                )


async def _ensure_connection(db):
    """Create or find the sample DB connection."""
    result = await db.execute(
        select(DatabaseConnection).where(DatabaseConnection.name == CONNECTION_NAME)
    )
    connection = result.scalar_one_or_none()

    if connection:
        logger.info("Auto-setup: connection '%s' already exists", CONNECTION_NAME)
        return connection

    logger.info("Auto-setup: creating connection '%s'...", CONNECTION_NAME)
    connection = await connection_service.create_connection(
        db,
        name=CONNECTION_NAME,
        connector_type="postgresql",
        connection_string=settings.sample_db_connection_string,
        default_schema="public",
    )
    await db.commit()
    logger.info("Auto-setup: connection created (id=%s)", connection.id)
    return connection


async def _seed_glossary(db, connection_id: uuid.UUID) -> None:
    """Seed glossary terms if none exist."""
    count = await db.scalar(
        select(func.count()).select_from(GlossaryTerm).where(
            GlossaryTerm.connection_id == connection_id
        )
    )
    if count and count > 0:
        logger.info("Auto-setup: glossary already has %d terms, skipping", count)
        return

    logger.info("Auto-setup: seeding %d glossary terms...", len(GLOSSARY_TERMS))
    for term_data in GLOSSARY_TERMS:
        db.add(GlossaryTerm(connection_id=connection_id, **term_data))
    await db.flush()


async def _seed_metrics(db, connection_id: uuid.UUID) -> None:
    """Seed metric definitions if none exist."""
    count = await db.scalar(
        select(func.count()).select_from(MetricDefinition).where(
            MetricDefinition.connection_id == connection_id
        )
    )
    if count and count > 0:
        logger.info("Auto-setup: metrics already has %d definitions, skipping", count)
        return

    logger.info("Auto-setup: seeding %d metrics...", len(METRICS))
    for metric_data in METRICS:
        db.add(MetricDefinition(connection_id=connection_id, **metric_data))
    await db.flush()


async def _seed_dictionary(db, connection_id: uuid.UUID) -> None:
    """Seed dictionary entries if none exist for any column."""
    # Check if any dictionary entries exist for columns in this connection
    count = await db.scalar(
        select(func.count())
        .select_from(DictionaryEntry)
        .join(CachedColumn, DictionaryEntry.column_id == CachedColumn.id)
        .join(CachedTable, CachedColumn.table_id == CachedTable.id)
        .where(CachedTable.connection_id == connection_id)
    )
    if count and count > 0:
        logger.info("Auto-setup: dictionary already has %d entries, skipping", count)
        return

    # Build column lookup: (table_name, column_name) -> column_id
    tables_result = await db.execute(
        select(CachedTable)
        .where(CachedTable.connection_id == connection_id)
        .options(selectinload(CachedTable.columns))
    )
    tables = list(tables_result.scalars().all())

    column_map: dict[tuple[str, str], uuid.UUID] = {}
    for table in tables:
        for col in table.columns:
            column_map[(table.table_name, col.column_name)] = col.id

    total = 0
    for (table_name, column_name), entries in DICTIONARY_ENTRIES.items():
        col_id = column_map.get((table_name, column_name))
        if not col_id:
            logger.warning(
                "Auto-setup: column %s.%s not found, skipping dictionary entries",
                table_name, column_name,
            )
            continue
        for entry_data in entries:
            db.add(DictionaryEntry(column_id=col_id, **entry_data))
            total += 1

    await db.flush()
    logger.info("Auto-setup: seeded %d dictionary entries", total)


async def _seed_knowledge(db, connection_id: uuid.UUID) -> None:
    """Seed a sample knowledge document if none exist."""
    count = await db.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(
            KnowledgeDocument.connection_id == connection_id
        )
    )
    if count and count > 0:
        logger.info(
            "Auto-setup: knowledge already has %d documents, skipping", count
        )
        return

    from app.services.knowledge_service import import_document

    logger.info("Auto-setup: importing knowledge document...")
    doc = await import_document(
        db,
        connection_id=connection_id,
        title=KNOWLEDGE_DOCUMENT["title"],
        content=KNOWLEDGE_DOCUMENT["content"],
        source_url=KNOWLEDGE_DOCUMENT["source_url"],
    )
    logger.info(
        "Auto-setup: knowledge document imported (%d chunks)", doc.chunk_count
    )


async def _generate_embeddings_background(connection_id: uuid.UUID) -> None:
    """Run embedding generation in the background with progress tracking."""
    from app.services.embedding_service import (
        count_items_needing_embeddings,
        generate_embeddings_for_connection,
    )
    from app.services.embedding_progress import (
        increment,
        mark_completed,
        mark_failed,
        start_tracking,
    )

    cid = str(connection_id)
    async with async_session_factory() as db:
        try:
            total = await count_items_needing_embeddings(db, connection_id)
            if total == 0:
                logger.info("Background embeddings: nothing to generate")
                return

            start_tracking(cid, total)
            logger.info(
                "Background embeddings: generating %d embeddings...", total
            )

            count = await generate_embeddings_for_connection(
                db, connection_id, on_progress=lambda: increment(cid)
            )
            await db.commit()

            mark_completed(cid)
            logger.info("Background embeddings: done (%d generated)", count)
        except Exception as e:
            await db.rollback()
            mark_failed(cid, str(e))
            logger.warning(
                "Background embeddings: failed (%s) — keyword-only matching "
                "will be used until embeddings are generated",
                e,
            )


def launch_background_embeddings(connection_id: uuid.UUID) -> None:
    """Fire-and-forget background embedding generation."""
    from app.services.embedding_progress import register_task

    task = asyncio.create_task(
        _generate_embeddings_background(connection_id),
        name=f"embed-{connection_id}",
    )
    register_task(str(connection_id), task)

"""Query Service — orchestrates the full NL → SQL → results pipeline."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.connector_registry import get_or_create_connector
from app.core.exceptions import AppError, SQLSafetyError
from app.core.telemetry import start_span
from app.db.models.query_history import QueryExecution
from app.llm.agents.error_handler import ErrorHandlerAgent
from app.llm.agents.query_composer import QueryComposerAgent
from app.llm.agents.result_interpreter import ResultInterpreterAgent
from app.llm.agents.sql_validator import SQLValidatorAgent, ValidationStatus
from app.llm.router import route
from app.semantic.context_builder import build_context
from app.services.connection_service import get_connection, get_decrypted_connection_string
from app.utils.sql_sanitizer import check_sql_safety


async def execute_nl_query(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
) -> dict:
    """Full pipeline: NL question → SQL → execute → interpret.

    Steps:
    1. Build semantic context
    2. Route to LLM provider/model
    3. Generate SQL (QueryComposerAgent)
    4. Validate SQL (SQLValidatorAgent)
    5. Execute query (via connector)
    6. Interpret results (ResultInterpreterAgent)
    7. Save to history

    Returns dict with all response fields.
    """
    conn = await get_connection(db, connection_id)
    connection_string = get_decrypted_connection_string(conn)

    # Step 1: Build context
    with start_span("build_context", **{"connection_id": str(connection_id)}):
        context = await build_context(db, connection_id, question, dialect=conn.connector_type)

    # Step 2: Route to LLM
    provider, llm_config = route(question)

    # Step 3: Generate SQL
    composer = QueryComposerAgent(provider, llm_config)
    with start_span("compose_sql", **{"llm.model": llm_config.model}):
        composer_output = await composer.compose(question, context.prompt_context)
    generated_sql = composer_output.generated_sql

    if not generated_sql:
        raise AppError("Failed to generate SQL query", status_code=422)

    # Step 4: Validate SQL
    validator = SQLValidatorAgent()
    # Build schema map for validation
    schema_tables = {}
    for lt in context.tables:
        schema_tables[lt.table.table_name.upper()] = [
            c.column_name.upper() for c in lt.columns
        ]

    with start_span("validate_sql"):
        validation = await validator.validate(generated_sql, schema_tables)

    final_sql = generated_sql
    retry_count = 0

    # If validation fails, try error handler
    if validation.status != ValidationStatus.VALID:
        error_handler = ErrorHandlerAgent(provider, llm_config)
        previous_attempts = [generated_sql]

        while validation.status != ValidationStatus.VALID and retry_count < 3:
            retry_count += 1
            resolution = await error_handler.handle_error(
                question=question,
                failed_sql=final_sql,
                error_message="; ".join(validation.issues),
                schema_context=context.prompt_context,
                attempt_number=retry_count,
                previous_attempts=previous_attempts,
            )

            if not resolution.should_retry or not resolution.corrected_sql:
                raise AppError(
                    f"SQL validation failed: {'; '.join(validation.issues)}",
                    status_code=422,
                )

            final_sql = resolution.corrected_sql
            previous_attempts.append(final_sql)
            validation = await validator.validate(final_sql, schema_tables)

    if validation.status == ValidationStatus.UNSAFE:
        raise AppError(
            f"SQL safety violation: {'; '.join(validation.issues)}",
            status_code=403,
        )

    # Step 5: Execute query
    connector = await get_or_create_connector(
        str(connection_id), conn.connector_type, connection_string
    )

    try:
        with start_span("execute_query", **{"db.dialect": conn.connector_type}):
            result = await connector.execute_query(
                final_sql,
                timeout_seconds=conn.max_query_timeout_seconds,
                max_rows=conn.max_rows,
            )
    except Exception as e:
        # Try error handler on execution errors
        error_handler = ErrorHandlerAgent(provider, llm_config)
        previous_attempts = [final_sql]

        for attempt in range(1, 4):
            resolution = await error_handler.handle_error(
                question=question,
                failed_sql=final_sql,
                error_message=str(e),
                schema_context=context.prompt_context,
                attempt_number=attempt,
                previous_attempts=previous_attempts,
            )

            if not resolution.should_retry or not resolution.corrected_sql:
                break

            final_sql = resolution.corrected_sql
            retry_count += 1
            previous_attempts.append(final_sql)

            # Re-validate before executing
            validation = await validator.validate(final_sql, schema_tables)
            if validation.status != ValidationStatus.VALID:
                continue

            try:
                result = await connector.execute_query(
                    final_sql,
                    timeout_seconds=conn.max_query_timeout_seconds,
                    max_rows=conn.max_rows,
                )
                break
            except Exception as retry_error:
                e = retry_error
                continue
        else:
            # Save failed execution to history
            execution = QueryExecution(
                connection_id=connection_id,
                natural_language=question,
                generated_sql=generated_sql,
                final_sql=final_sql,
                execution_status="error",
                error_message=str(e),
                retry_count=retry_count,
                llm_provider=provider.provider_type.value,
                llm_model=llm_config.model,
            )
            db.add(execution)
            await db.flush()
            raise AppError(f"Query execution failed after {retry_count} retries: {e}")

    # Step 6: Interpret results
    summary = None
    highlights = []
    followups = []

    if result.rows:
        interpreter = ResultInterpreterAgent(provider, llm_config)
        with start_span("interpret_results", **{"row_count": result.row_count}):
            interpretation = await interpreter.interpret(
                question=question,
                sql=final_sql,
                columns=result.columns,
                rows=result.rows,
                row_count=result.row_count,
            )
        summary = interpretation.summary
        highlights = interpretation.highlights
        followups = interpretation.suggested_followups

    # Step 7: Save to history
    execution = QueryExecution(
        connection_id=connection_id,
        natural_language=question,
        generated_sql=generated_sql,
        final_sql=final_sql,
        execution_status="success",
        row_count=result.row_count,
        execution_time_ms=result.execution_time_ms,
        retry_count=retry_count,
        result_summary=summary,
        llm_provider=provider.provider_type.value,
        llm_model=llm_config.model,
    )
    db.add(execution)
    await db.flush()

    return {
        "id": execution.id,
        "question": question,
        "generated_sql": generated_sql,
        "final_sql": final_sql,
        "explanation": composer_output.explanation,
        "columns": result.columns,
        "column_types": result.column_types,
        "rows": _serialize_rows(result.rows),
        "row_count": result.row_count,
        "execution_time_ms": result.execution_time_ms,
        "truncated": result.truncated,
        "summary": summary,
        "highlights": highlights,
        "suggested_followups": followups,
        "llm_provider": provider.provider_type.value,
        "llm_model": llm_config.model,
        "retry_count": retry_count,
    }


async def generate_sql_only(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
) -> dict:
    """Generate SQL without executing it."""
    conn = await get_connection(db, connection_id)
    context = await build_context(db, connection_id, question, dialect=conn.connector_type)
    provider, llm_config = route(question)
    composer = QueryComposerAgent(provider, llm_config)
    output = await composer.compose(question, context.prompt_context)

    return {
        "generated_sql": output.generated_sql,
        "explanation": output.explanation,
        "confidence": output.confidence,
        "tables_used": output.tables_used,
        "assumptions": output.assumptions,
    }


async def execute_raw_sql(
    db: AsyncSession,
    connection_id: uuid.UUID,
    sql: str,
    original_question: str | None = None,
) -> dict:
    """Execute user-provided SQL directly (no LLM generation).

    Steps:
    1. Safety check (block DDL/DML)
    2. Execute query via connector
    3. Save to history

    No LLM retry on error — the user can fix the SQL manually.
    """
    # Step 1: Safety check
    safety_issues = check_sql_safety(sql)
    if safety_issues:
        raise SQLSafetyError("; ".join(safety_issues))

    conn = await get_connection(db, connection_id)
    connection_string = get_decrypted_connection_string(conn)

    # Step 2: Execute query
    connector = await get_or_create_connector(
        str(connection_id), conn.connector_type, connection_string
    )

    try:
        result = await connector.execute_query(
            sql,
            timeout_seconds=conn.max_query_timeout_seconds,
            max_rows=conn.max_rows,
        )
    except Exception as e:
        # Save failed execution to history
        execution = QueryExecution(
            connection_id=connection_id,
            natural_language=original_question or "(manual SQL)",
            generated_sql=None,
            final_sql=sql,
            execution_status="error",
            error_message=str(e),
            retry_count=0,
        )
        db.add(execution)
        await db.flush()
        raise AppError(f"Query execution failed: {e}") from e

    # Step 3: Interpret results (LLM summary + follow-ups)
    summary = None
    highlights = []
    followups = []
    llm_provider_name = "manual"
    llm_model_name = "manual"

    question_text = original_question or "(manual SQL)"

    if result.rows:
        try:
            provider, llm_config = route(question_text)
            interpreter = ResultInterpreterAgent(provider, llm_config)
            interpretation = await interpreter.interpret(
                question=question_text,
                sql=sql,
                columns=result.columns,
                rows=result.rows,
                row_count=result.row_count,
            )
            summary = interpretation.summary
            highlights = interpretation.highlights
            followups = interpretation.suggested_followups
            llm_provider_name = provider.provider_type.value
            llm_model_name = llm_config.model
        except Exception:
            pass  # Interpretation is best-effort; don't fail the query

    # Step 4: Save to history
    execution = QueryExecution(
        connection_id=connection_id,
        natural_language=question_text,
        generated_sql=None,
        final_sql=sql,
        execution_status="success",
        row_count=result.row_count,
        execution_time_ms=result.execution_time_ms,
        retry_count=0,
        result_summary=summary,
        llm_provider=llm_provider_name,
        llm_model=llm_model_name,
    )
    db.add(execution)
    await db.flush()

    return {
        "id": execution.id,
        "question": question_text,
        "generated_sql": sql,
        "final_sql": sql,
        "explanation": "User-provided SQL executed directly.",
        "columns": result.columns,
        "column_types": result.column_types,
        "rows": _serialize_rows(result.rows),
        "row_count": result.row_count,
        "execution_time_ms": result.execution_time_ms,
        "truncated": result.truncated,
        "summary": summary,
        "highlights": highlights,
        "suggested_followups": followups,
        "llm_provider": llm_provider_name,
        "llm_model": llm_model_name,
        "retry_count": 0,
    }


def _serialize_rows(rows: list[list]) -> list[list]:
    """Ensure all row values are JSON-serializable."""
    serialized = []
    for row in rows:
        serialized_row = []
        for val in row:
            if hasattr(val, "isoformat"):
                serialized_row.append(val.isoformat())
            elif isinstance(val, bytes):
                serialized_row.append(val.hex())
            else:
                serialized_row.append(val)
        serialized.append(serialized_row)
    return serialized

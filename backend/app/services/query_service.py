"""Query Service — orchestrates the full NL → SQL → results pipeline."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.connector_registry import get_or_create_connector
from app.core.auth import AuthContext
from app.core.exceptions import AppError, SQLSafetyError
from app.core.telemetry import start_span
from app.db.models.query_history import QueryExecution
from app.llm.agents.error_handler import ErrorHandlerAgent
from app.llm.agents.query_composer import QueryComposerAgent
from app.llm.agents.result_interpreter import ResultInterpreterAgent
from app.llm.agents.sql_validator import SQLValidatorAgent, ValidationStatus
from app.llm.router import route
from app.semantic.context_builder import build_context
from app.services import audit_service, cost_service, policy_service
from app.services.connection_service import get_connection, get_decrypted_connection_string
from app.services.lineage_service import dialect_for
from app.services.policy_service import PolicyViolationError
from app.utils.sql_sanitizer import check_sql_safety


async def _enforce_policy_sql(
    db: AsyncSession,
    ctx: AuthContext,
    connection_id: uuid.UUID,
    eff: "policy_service.EffectivePolicy | None",
    sql: str,
    dialect: str | None,
    *,
    question: str | None = None,
) -> str:
    """Apply a connection's data policy to ``sql`` before execution.

    Returns the (possibly row-filtered) SQL, or — on a policy block — records a
    ``query.blocked`` audit event and raises a 403 with the reason. Returns
    ``sql`` unchanged when no policy applies.
    """
    if eff is None:
        return sql
    try:
        return policy_service.enforce_sql(eff, sql, dialect)
    except PolicyViolationError as pv:
        await audit_service.record(
            db,
            organization_id=ctx.organization_id,
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user_id,
            event_type=audit_service.QUERY_BLOCKED,
            payload={
                "connection_id": str(connection_id),
                "question": question,
                "sql": sql,
                "reason": pv.reason,
                "policy": True,
            },
        )
        raise AppError(f"Blocked by data policy: {pv.reason}", status_code=403) from pv


async def execute_nl_query(
    db: AsyncSession,
    connection_id: uuid.UUID,
    question: str,
    ctx: AuthContext,
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
    conn = await get_connection(db, connection_id, ctx)
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
        await audit_service.record(
            db,
            organization_id=ctx.organization_id,
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user_id,
            event_type=audit_service.QUERY_BLOCKED,
            payload={
                "connection_id": str(connection_id),
                "question": question,
                "sql": final_sql,
                "reason": "; ".join(validation.issues),
            },
        )
        raise AppError(
            f"SQL safety violation: {'; '.join(validation.issues)}",
            status_code=403,
        )

    # Step 5: Execute query (enforcing the connection's data policy first)
    connector = await get_or_create_connector(
        str(connection_id), conn.connector_type, connection_string
    )
    eff_policy = await policy_service.resolve_effective(db, connection_id, ctx.role)
    dialect = dialect_for(conn.connector_type)
    pol_max_rows, pol_timeout = policy_service.effective_limits(
        eff_policy, conn.max_rows, conn.max_query_timeout_seconds
    )

    # A policy block here is a hard stop (raises 403) — it must happen outside
    # the error-handler retry loop so it is never treated as a fixable error.
    run_sql = await _enforce_policy_sql(
        db, ctx, connection_id, eff_policy, final_sql, dialect, question=question
    )
    try:
        with start_span("execute_query", **{"db.dialect": conn.connector_type}):
            result = await connector.execute_query(
                run_sql,
                timeout_seconds=pol_timeout,
                max_rows=pol_max_rows,
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

            # Re-apply the policy to each corrected SQL so row filters / blocks
            # can't be bypassed by an LLM rewrite. A block (403) propagates out.
            run_sql = await _enforce_policy_sql(
                db, ctx, connection_id, eff_policy, final_sql, dialect, question=question
            )
            try:
                result = await connector.execute_query(
                    run_sql,
                    timeout_seconds=pol_timeout,
                    max_rows=pol_max_rows,
                )
                break
            except Exception as retry_error:
                e = retry_error
                continue
        else:
            # Save failed execution to history
            execution = QueryExecution(
                organization_id=ctx.organization_id,
                connection_id=connection_id,
                user_id=ctx.user_id,
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

    # Apply policy column masking in place so redacted PII never reaches the
    # interpreter LLM, the response, or persisted history.
    result.rows, _ = policy_service.mask_result(eff_policy, result.columns, result.rows)

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
        organization_id=ctx.organization_id,
        connection_id=connection_id,
        user_id=ctx.user_id,
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

    await audit_service.record(
        db,
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.QUERY_EXECUTED,
        payload={
            "connection_id": str(connection_id),
            "query_execution_id": str(execution.id),
            "question": question,
            "sql": final_sql,
            "row_count": result.row_count,
        },
    )

    await cost_service.record_execution_cost(
        db,
        execution=execution,
        ctx=ctx,
        connector_type=conn.connector_type,
        stats=result.stats,
        final_sql=final_sql,
    )

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
    ctx: AuthContext,
) -> dict:
    """Generate SQL without executing it."""
    conn = await get_connection(db, connection_id, ctx)
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
    ctx: AuthContext,
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
        await audit_service.record(
            db,
            organization_id=ctx.organization_id,
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user_id,
            event_type=audit_service.QUERY_BLOCKED,
            payload={
                "connection_id": str(connection_id),
                "sql": sql,
                "reason": "; ".join(safety_issues),
            },
        )
        raise SQLSafetyError("; ".join(safety_issues))

    conn = await get_connection(db, connection_id, ctx)
    connection_string = get_decrypted_connection_string(conn)

    # Step 2: Enforce the data policy, then execute.
    connector = await get_or_create_connector(
        str(connection_id), conn.connector_type, connection_string
    )
    eff_policy = await policy_service.resolve_effective(db, connection_id, ctx.role)
    dialect = dialect_for(conn.connector_type)
    pol_max_rows, pol_timeout = policy_service.effective_limits(
        eff_policy, conn.max_rows, conn.max_query_timeout_seconds
    )
    run_sql = await _enforce_policy_sql(
        db, ctx, connection_id, eff_policy, sql, dialect, question=original_question
    )

    try:
        result = await connector.execute_query(
            run_sql,
            timeout_seconds=pol_timeout,
            max_rows=pol_max_rows,
        )
    except Exception as e:
        # Save failed execution to history
        execution = QueryExecution(
            organization_id=ctx.organization_id,
            connection_id=connection_id,
            user_id=ctx.user_id,
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

    # Apply policy column masking in place before interpretation / persistence.
    result.rows, _ = policy_service.mask_result(eff_policy, result.columns, result.rows)

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
        organization_id=ctx.organization_id,
        connection_id=connection_id,
        user_id=ctx.user_id,
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

    await cost_service.record_execution_cost(
        db,
        execution=execution,
        ctx=ctx,
        connector_type=conn.connector_type,
        stats=result.stats,
        final_sql=sql,
    )

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

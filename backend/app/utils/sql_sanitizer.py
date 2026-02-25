import re

# Patterns that indicate dangerous SQL operations
_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # DDL
    (re.compile(r"\bDROP\b", re.IGNORECASE), "DROP statements are not allowed"),
    (re.compile(r"\bALTER\b", re.IGNORECASE), "ALTER statements are not allowed"),
    (re.compile(r"\bCREATE\b", re.IGNORECASE), "CREATE statements are not allowed"),
    (re.compile(r"\bTRUNCATE\b", re.IGNORECASE), "TRUNCATE statements are not allowed"),
    # DML
    (re.compile(r"\bINSERT\b", re.IGNORECASE), "INSERT statements are not allowed"),
    (re.compile(r"\bUPDATE\b\s", re.IGNORECASE), "UPDATE statements are not allowed"),
    (re.compile(r"\bDELETE\b\s+FROM\b", re.IGNORECASE), "DELETE statements are not allowed"),
    (re.compile(r"\bMERGE\b", re.IGNORECASE), "MERGE statements are not allowed"),
    # Admin / dangerous
    (re.compile(r"\bGRANT\b", re.IGNORECASE), "GRANT statements are not allowed"),
    (re.compile(r"\bREVOKE\b", re.IGNORECASE), "REVOKE statements are not allowed"),
    (re.compile(r"\bCOPY\b", re.IGNORECASE), "COPY statements are not allowed"),
    (re.compile(r"\bEXECUTE\b", re.IGNORECASE), "EXECUTE statements are not allowed"),
    # Postgres-specific dangerous functions
    (re.compile(r"\bpg_sleep\b", re.IGNORECASE), "pg_sleep is not allowed"),
    (re.compile(r"\bpg_terminate_backend\b", re.IGNORECASE), "pg_terminate_backend is not allowed"),
    (re.compile(r"\bpg_cancel_backend\b", re.IGNORECASE), "pg_cancel_backend is not allowed"),
    (re.compile(r"\bdblink\b", re.IGNORECASE), "dblink is not allowed"),
    # BigQuery-specific
    (re.compile(r"\bEXPORT\s+DATA\b", re.IGNORECASE), "EXPORT DATA is not allowed"),
    (re.compile(r"\bLOAD\s+DATA\b", re.IGNORECASE), "LOAD DATA is not allowed"),
    # Databricks-specific
    (re.compile(r"\bCOPY\s+INTO\b", re.IGNORECASE), "COPY INTO is not allowed"),
    (re.compile(r"\bOPTIMIZE\b", re.IGNORECASE), "OPTIMIZE is not allowed"),
    (re.compile(r"\bVACUUM\b", re.IGNORECASE), "VACUUM is not allowed"),
    # Stacked queries (semicolon followed by another statement)
    (
        re.compile(r";\s*\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b", re.IGNORECASE),
        "Multiple statements (stacked queries) are not allowed",
    ),
]


def check_sql_safety(sql: str) -> list[str]:
    """Check SQL for dangerous patterns. Returns list of issues found, empty if safe."""
    issues: list[str] = []
    # Strip comments before checking
    cleaned = _strip_sql_comments(sql)
    for pattern, message in _BLOCKED_PATTERNS:
        if pattern.search(cleaned):
            issues.append(message)
    return issues


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments to prevent bypass via comment injection."""
    # Remove single-line comments
    sql = re.sub(r"--[^\n]*", "", sql)
    # Remove multi-line comments
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql

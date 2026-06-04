import pytest

from app.utils.sql_sanitizer import check_sql_safety


def test_plain_select_is_safe():
    assert check_sql_safety("SELECT * FROM exposures WHERE stage = 1") == []


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE exposures",
        "ALTER TABLE exposures ADD COLUMN x int",
        "CREATE TABLE t (id int)",
        "TRUNCATE exposures",
        "INSERT INTO exposures VALUES (1)",
        "UPDATE exposures SET stage = 2",
        "DELETE FROM exposures",
        "MERGE INTO exposures USING s ON true",
        "GRANT SELECT ON exposures TO public",
        "REVOKE SELECT ON exposures FROM public",
        "SELECT pg_sleep(10)",
        "SELECT * FROM dblink('...', '...')",
        "EXPORT DATA OPTIONS(uri='gs://x') AS SELECT 1",
        "LOAD DATA INTO t",
        "COPY INTO t FROM '/x'",
        "OPTIMIZE t",
        "VACUUM t",
    ],
)
def test_dangerous_statements_blocked(sql):
    assert check_sql_safety(sql), f"expected {sql!r} to be flagged"


def test_stacked_queries_blocked():
    issues = check_sql_safety("SELECT 1; DROP TABLE t")
    assert any("stacked" in i.lower() for i in issues)


def test_comment_injection_does_not_hide_keyword():
    # The DROP is revealed once comments are stripped.
    issues = check_sql_safety("SELECT 1 -- harmless\n; DROP TABLE t")
    assert issues


def test_block_inside_block_comment():
    issues = check_sql_safety("SELECT 1 /* DROP TABLE t */ FROM x")
    # Comment is stripped, so the DROP inside it should NOT be flagged.
    assert issues == []

"""Unit tests for lineage_service.extract_refs (pure sqlglot parsing, no DB)."""

import pytest

from app.db.models.artifact_dependency import REF_COLUMN, REF_TABLE
from app.services import lineage_service as svc

# extract_refs degrades to a no-op without sqlglot (the optional [lineage] extra);
# these tests assert the *populated* path, so skip the module when it's absent.
pytest.importorskip("sqlglot")


def _tables(refs):
    return {r.table_name for r in refs if r.ref_kind == REF_TABLE}


def _cols(refs):
    return {(r.table_name, r.column_name) for r in refs if r.ref_kind == REF_COLUMN}


def test_single_table_columns_attributed():
    refs = svc.extract_refs("SELECT a, b FROM exposures", "postgres")
    assert _tables(refs) == {"exposures"}
    assert _cols(refs) == {("exposures", "a"), ("exposures", "b")}


def test_join_with_aliases_resolves_qualifiers():
    sql = "SELECT e.id, c.name FROM exposures e JOIN counterparties c ON e.cp_id = c.id"
    refs = svc.extract_refs(sql, "postgres")
    assert _tables(refs) == {"exposures", "counterparties"}
    cols = _cols(refs)
    assert ("exposures", "id") in cols
    assert ("counterparties", "name") in cols
    assert ("counterparties", "id") in cols


def test_schema_qualified_table():
    refs = svc.extract_refs("SELECT * FROM public.facilities", "postgres")
    table_refs = [r for r in refs if r.ref_kind == REF_TABLE]
    assert table_refs[0].table_name == "facilities"
    assert table_refs[0].schema_name == "public"


def test_unparseable_sql_returns_empty():
    assert svc.extract_refs("this is not sql ;;;(", "postgres") == []


def test_empty_sql_returns_empty():
    assert svc.extract_refs("", "postgres") == []
    assert svc.extract_refs("   ", "postgres") == []


def test_dialect_mapping():
    assert svc.dialect_for("postgresql") == "postgres"
    assert svc.dialect_for("bigquery") == "bigquery"
    assert svc.dialect_for(None) is None
    assert svc.dialect_for("unknown-db") is None

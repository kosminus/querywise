"""Unit tests for catalog_service ranking + score combination (no DB)."""

from app.services import catalog_service as svc


def test_combine_certified_boost():
    plain, _ = svc._combine(0.5, 0.5, None)
    certified, _ = svc._combine(0.5, 0.5, "certified")
    assert certified == plain + svc._CERT_BOOST


def test_combine_reason_picks_dominant_signal():
    _, reason = svc._combine(0.9, 0.1, None)
    assert reason == "embedding"
    _, reason = svc._combine(0.1, 0.9, None)
    assert reason == "keyword"


def test_rank_certified_first_then_score():
    hits = [
        svc.CatalogHit(type="metric", id="1", name="low", status="draft", score=0.9),
        svc.CatalogHit(type="metric", id="2", name="cert", status="certified", score=0.2),
        svc.CatalogHit(type="metric", id="3", name="mid", status="draft", score=0.5),
    ]
    ranked = svc.rank_hits(hits, limit=10)
    assert [h.id for h in ranked] == ["2", "1", "3"]  # certified first, then by score desc


def test_rank_respects_limit():
    hits = [svc.CatalogHit(type="table", id=str(i), name=f"t{i}", score=i) for i in range(5)]
    assert len(svc.rank_hits(hits, limit=2)) == 2


def test_all_types_present():
    assert set(svc.ALL_TYPES) >= {"table", "column", "metric", "glossary", "saved_query"}

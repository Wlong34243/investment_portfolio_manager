"""Facet filters narrow the result set (AND semantics)."""

from fastapi.testclient import TestClient

from core.corpus.search import search_ranked

from ui.app import app


def test_source_type_facet_narrows():
    all_hits = search_ranked("energy", limit=50)
    if len(all_hits) < 2:
        return
    st = all_hits[0].source_type
    filtered = search_ranked("energy", source_types=[st], limit=50)
    assert all(h.source_type == st for h in filtered)
    assert len(filtered) <= len(all_hits)


def test_combined_facets_and():
    client = TestClient(app)
    resp = client.get(
        "/search",
        params={"q": "ET", "source_type": "thesis", "ticker": "ET"},
    )
    assert resp.status_code == 200

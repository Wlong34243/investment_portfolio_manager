"""Provenance badges on search hits."""

from fastapi.testclient import TestClient

from core.corpus.search import provenance_badge, search_ranked

from ui.app import app


def test_podcast_summary_badge_model_output():
    hits = search_ranked("portfolio", source_types=["podcast_summary"], limit=5)
    if not hits:
        return
    assert provenance_badge(hits[0]) == "model_output"


def test_model_output_badge_in_html():
    hits = search_ranked("portfolio", source_types=["podcast_summary"], limit=3)
    if not hits:
        return
    client = TestClient(app)
    resp = client.get("/search", params={"q": "portfolio", "source_type": "podcast_summary"})
    assert resp.status_code == 200
    assert "model output" in resp.text.lower()

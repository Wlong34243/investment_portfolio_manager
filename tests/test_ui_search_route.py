"""Corpus search route smoke tests."""

from fastapi.testclient import TestClient

from ui.app import app


def test_search_empty_q_renders_form():
    client = TestClient(app)
    resp = client.get("/search")
    assert resp.status_code == 200
    assert "Corpus Search" in resp.text
    assert "Enter a query" in resp.text
    assert "BM25" in resp.text


def test_search_with_query():
    client = TestClient(app)
    resp = client.get("/search", params={"q": "lake"})
    assert resp.status_code == 200
    assert "hit" in resp.text.lower() or "No hits" in resp.text

"""XSS escaping on search queries and snippets."""

from core.corpus.search import snippet_html
from fastapi.testclient import TestClient

from ui.app import app


def test_query_script_escaped():
    client = TestClient(app)
    payload = "<script>alert(1)</script>"
    resp = client.get("/search", params={"q": payload})
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text or payload not in resp.text


def test_snippet_mark_survives_escape():
    html = snippet_html("foo <mark>bar</mark> baz")
    assert "<mark>bar</mark>" in str(html)
    assert "<script>" not in str(html)

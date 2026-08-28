"""Document reader route."""

from fastapi.testclient import TestClient

from core.corpus.search import search_ranked

from ui.app import app


def test_doc_route_renders():
    hits = search_ranked("portfolio", limit=1)
    if not hits:
        return
    h = hits[0]
    client = TestClient(app)
    resp = client.get(f"/doc/{h.doc_id}", params={"chunk": h.chunk_id})
    assert resp.status_code == 200
    assert h.path.split("/")[-1] in resp.text or "line-" in resp.text
    assert f'id="line-{h.line_start}"' in resp.text or "highlight" in resp.text

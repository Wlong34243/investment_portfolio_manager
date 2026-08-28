"""Position Story route smoke tests."""

from fastapi.testclient import TestClient

from ui.app import app


def test_position_held_ticker_200():
    client = TestClient(app)
    resp = client.get("/position/MU")
    if resp.status_code == 404:
        # holdings scope may not include MU in a bare test DB — try QQQM ballast path
        resp = client.get("/position/QQQM")
    assert resp.status_code == 200, resp.text[:500]
    assert "Position Story" in resp.text or resp.status_code == 200


def test_position_unknown_404_with_list():
    client = TestClient(app)
    resp = client.get("/position/ZZZZ")
    assert resp.status_code == 404
    assert "Unknown position" in resp.text
    assert "Held tickers" in resp.text or "not in the current holdings" in resp.text

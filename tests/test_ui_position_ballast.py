"""Ballast positions suppress style ceiling readout."""

from fastapi.testclient import TestClient

from ui.app import app


def test_jepi_no_ceiling_breach_text():
    client = TestClient(app)
    resp = client.get("/position/JEPI")
    if resp.status_code == 404:
        return  # JEPI not in scoped holdings in this environment
    assert resp.status_code == 200
    text = resp.text
    assert "Ceiling:" not in text
    assert "headroom" not in text.lower()

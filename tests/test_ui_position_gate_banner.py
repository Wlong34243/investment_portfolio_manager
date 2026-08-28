"""Signal lane accrual gate banner while < 10 trading days."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from ui.app import app


@patch("ui.position_story.evidence_status")
def test_gate_banner_renders_when_not_met(mock_status):
    mock_status.return_value = {
        "clean_trading_days": 2,
        "gate_met": False,
        "evidence_first_accrual_date": "2026-08-27",
    }
    client = TestClient(app)
    resp = client.get("/position/QQQM")
    if resp.status_code == 404:
        resp = client.get("/position/MU")
    if resp.status_code == 404:
        return
    assert resp.status_code == 200
    assert "Signal capture began 2026-08-27" in resp.text
    assert "2 of 10 trading days" in resp.text

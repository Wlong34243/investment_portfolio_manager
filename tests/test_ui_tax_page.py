"""Tax page — formatted money columns, no raw ledger floats in cells."""

import re

from fastapi.testclient import TestClient

from ui.app import app

_RAW_FLOAT = re.compile(r"0\.\d{6,}")


def test_tax_page_renders():
    client = TestClient(app)
    resp = client.get("/tax")
    assert resp.status_code == 200
    assert "Tax Control" in resp.text


def test_tax_lots_no_raw_floats_in_table():
    client = TestClient(app)
    resp = client.get("/tax")
    assert resp.status_code == 200
    # Delta-bar inline widths are out of scope; scan table body only.
    tbody = resp.text.split("<tbody>", 1)[-1].split("</tbody>", 1)[0] if "<tbody>" in resp.text else ""
    if not tbody.strip():
        return
    assert _RAW_FLOAT.search(tbody) is None, _RAW_FLOAT.findall(tbody)[:3]


def test_tax_disallowed_loss_uses_money_filter():
    client = TestClient(app)
    resp = client.get("/tax")
    if "Disallowed Loss" not in resp.text:
        return
    assert "Disallowed Loss" in resp.text
    # Formatted dollars use $ or em-dash, not bare floats in adjacent cells.
    idx = resp.text.find("Disallowed Loss")
    snippet = resp.text[idx : idx + 800]
    for cell in re.findall(r"<td[^>]*>([^<]+)</td>", snippet):
        if cell.strip() and cell.strip() not in {"—", "-"}:
            assert "$" in cell or not _RAW_FLOAT.search(cell), cell

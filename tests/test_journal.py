"""Journal rationale-loop unit tests."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_journal_none_is_blank():
    from core.journal.propose import Proposal

    p = Proposal(
        cluster_id="x",
        fingerprint="fp",
        fill_date=date(2026, 1, 1),
        sell_tickers=["A"],
        buy_tickers=["B"],
        match_strength="none",
        proposal_text="",
    )
    assert p.proposal_text == ""
    assert len(p.proposal_text) == 0


def test_journal_provenance_forced():
    from core.journal import persist

    assert persist.PROVENANCE_RECONCILE == "reconstructed_after"
    # batch_reject_none must set reconstructed_after, never declared_before
    import inspect

    src = inspect.getsource(persist.batch_reject_none)
    assert "PROVENANCE_RECONCILE" in src
    assert "declared_before" not in src


def test_journal_cluster_supersets():
    """Five nested rows same Date → one widest cluster."""
    from tasks.compute_rotation_attribution import find_superseded_groups

    rows = [
        {"Trade_Log_ID": "1", "Date": "2026-08-03", "Sell_Ticker": "JEPI", "Buy_Ticker": "VST"},
        {
            "Trade_Log_ID": "2",
            "Date": "2026-08-03",
            "Sell_Ticker": "JEPI,JPIE",
            "Buy_Ticker": "VST,IBM",
        },
        {
            "Trade_Log_ID": "3",
            "Date": "2026-08-03",
            "Sell_Ticker": "JEPI,JPIE,KRE",
            "Buy_Ticker": "VST,IBM,XOM",
        },
        {
            "Trade_Log_ID": "4",
            "Date": "2026-08-03",
            "Sell_Ticker": "JEPI,JPIE,KRE,APO",
            "Buy_Ticker": "VST,IBM,XOM,PWR",
        },
        {
            "Trade_Log_ID": "5",
            "Date": "2026-08-03",
            "Sell_Ticker": "JEPI,JPIE,KRE,APO,ES",
            "Buy_Ticker": "VST,IBM,XOM,PWR,VRT",
        },
    ]
    superseded, _groups = find_superseded_groups(rows)
    widest = [r["Trade_Log_ID"] for r in rows if r["Trade_Log_ID"] not in superseded]
    assert widest == ["5"]
    assert len(superseded) == 4


def test_no_gemini_in_journal():
    root = Path(__file__).resolve().parents[1] / "core" / "journal"
    for p in root.glob("*.py"):
        text = p.read_text(encoding="utf-8").lower()
        assert "ask_gemini" not in text
        assert "import google" not in text

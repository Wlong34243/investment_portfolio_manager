"""
tests/test_moment_windows.py — Unit tests for utils/moment_windows.py.

Run with:  python -m pytest tests/test_moment_windows.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.moment_windows import find_windows, load_cues, load_ticker_aliases


TICKER_ALIASES = {"NVDA": ["NVDA", "Nvidia"], "AAPL": ["AAPL", "Apple"]}


def _cue(category, pattern, kind="simple", **extra):
    return {"category": category, "kind": kind, "pattern": pattern, **extra}


# ---------------------------------------------------------------------------
# Overlapping-window merge
# ---------------------------------------------------------------------------

class TestOverlapMerge:
    def test_two_nearby_hits_merge_into_one_window(self):
        transcript = "x" * 100 + " I was wrong about that call " + "y" * 50 + " we sold it all " + "z" * 100
        cues = [_cue("reversal", "I was wrong about"), _cue("reversal", "we sold")]
        windows = find_windows(transcript, cues, radius=60)
        assert len(windows) == 1
        assert windows[0]["char_start"] <= 100
        assert len(windows[0]["matched_cues"]) == 2

    def test_far_apart_hits_stay_separate(self):
        transcript = "I was wrong about that. " + ("filler " * 1000) + "we sold everything today."
        cues = [_cue("reversal", "I was wrong about"), _cue("reversal", "we sold")]
        windows = find_windows(transcript, cues, radius=50)
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# specific_claim ticker-proximity requirement
# ---------------------------------------------------------------------------

class TestTickerProximity:
    def test_matches_when_ticker_nearby(self):
        transcript = "so nvidia is trading at a huge multiple right now honestly"
        cues = [_cue("specific_claim", "trading at", kind="ticker_proximity", proximity_chars=40)]
        windows = find_windows(transcript, cues, radius=50, ticker_aliases=TICKER_ALIASES)
        assert len(windows) == 1
        assert windows[0]["cue_category"] == "specific_claim"

    def test_no_match_without_ticker_nearby(self):
        transcript = "this random mattress company is trading at a huge discount to peers"
        cues = [_cue("specific_claim", "trading at", kind="ticker_proximity", proximity_chars=40)]
        windows = find_windows(transcript, cues, radius=50, ticker_aliases=TICKER_ALIASES)
        assert windows == []


# ---------------------------------------------------------------------------
# Negative test — sponsor read must not match
# ---------------------------------------------------------------------------

class TestSponsorReadRejected:
    def test_sponsor_read_for_mattress_company_does_not_match(self):
        transcript = (
            "this episode is brought to you by casper mattresses, trading at "
            "a great price this month with free shipping and a 100 night trial"
        )
        cues = [_cue("specific_claim", "trading at", kind="ticker_proximity", proximity_chars=40)]
        windows = find_windows(transcript, cues, radius=50, ticker_aliases=TICKER_ALIASES)
        assert windows == []


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------

class TestGuardrail:
    def test_truncates_to_40_highest_density_windows(self):
        # 50 well-separated hits so none merge; guardrail should cap at 40.
        parts = []
        for i in range(50):
            parts.append("filler " * 20)
            parts.append("we sold the position")
        transcript = "".join(parts)
        cues = [_cue("reversal", "we sold")]
        windows = find_windows(transcript, cues, radius=30)
        assert len(windows) == 40


# ---------------------------------------------------------------------------
# disagreement speaker-marker proximity + honest positional speaker field
# ---------------------------------------------------------------------------

class TestDisagreement:
    def test_disagreement_requires_speaker_marker_nearby(self):
        transcript = "some setup text >> no wait, I disagree with that take entirely"
        cues = [_cue("disagreement", "I disagree", kind="speaker_proximity",
                      proximity_chars=50, speaker_marker=">>")]
        windows = find_windows(transcript, cues, radius=30)
        assert len(windows) == 1
        assert windows[0]["speaker"] == "turn_1"

    def test_disagreement_without_speaker_marker_does_not_match(self):
        transcript = "he calmly said I disagree with that take entirely, no drama"
        cues = [_cue("disagreement", "I disagree", kind="speaker_proximity",
                      proximity_chars=10, speaker_marker=">>")]
        windows = find_windows(transcript, cues, radius=30)
        assert windows == []


# ---------------------------------------------------------------------------
# Config loaders — smoke test against the real files on disk
# ---------------------------------------------------------------------------

class TestConfigLoaders:
    def test_load_cues_returns_all_five_categories(self):
        cues = load_cues()
        categories = {c["category"] for c in cues}
        assert categories == {
            "reversal", "non_consensus", "position_disclosure",
            "specific_claim", "disagreement",
        }

    def test_load_ticker_aliases_has_no_stripped_common_word_tickers(self):
        aliases = load_ticker_aliases()
        # These tickers collide with ordinary English words and must not
        # appear as a bare alias for their own ticker.
        for ticker in ("SNOW", "GILD", "ES", "ET", "NOW", "META"):
            assert ticker not in aliases[ticker], (
                "%s should not list its own bare ticker as an alias" % ticker
            )

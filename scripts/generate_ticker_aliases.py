"""
scripts/generate_ticker_aliases.py — regenerate data/ticker_aliases.json from
a public S&P 500 constituents dataset, merged with the hand-curated aliases
for held positions and a small supplement of common ADRs.

Purpose : v1 of data/ticker_aliases.json covered only the 37 held tickers,
          which structurally prevented ZERO_EXPOSURE moment discovery (the
          specific_claim ticker-proximity gate could only ever fire next to
          a name Bill already owns). This pulls in company names for the
          full S&P 500 so the gate can fire on names he doesn't hold.
Inputs  : https://raw.githubusercontent.com/datasets/s-and-p-500-companies/
          master/data/constituents.csv (Symbol, Security columns) — a
          long-standing public dataset, not a new paid vendor. FMP's own
          /stable/sp500-constituent is gated to a higher subscription tier
          (confirmed 402 on the current key) or this would extend
          utils/fmp_client.py instead per repo convention.
Outputs : data/ticker_aliases.json — same shape as before (ticker -> [alias
          strings]), now ~500+ entries. Existing hand-curated multi-alias
          entries for held tickers are preserved and only ADDED to, never
          overwritten, so richer aliases like GOOG's ["GOOG","GOOGL",
          "Google","Alphabet"] survive a regeneration.
Depends : Standard library only (urllib, csv, json, re).
Usage   : python scripts/generate_ticker_aliases.py
          Network call is a one-time, dev-time data-generation step, not
          part of any runtime extraction path -- the output is committed
          static data, same treatment as data/moment_cues.json.
"""

import csv
import io
import json
import os
import re
import sys
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "master/data/constituents.csv"
)
ALIASES_PATH = os.path.join(_REPO_ROOT, "data", "ticker_aliases.json")

# Suffixes safe to strip when the remainder is still multi-word, or when the
# remainder (lowercased) is not in COMMON_WORD_BLOCKLIST below. Longest
# first so "Corporation" doesn't leave a dangling " Corp".
STRIPPABLE_SUFFIXES = [
    " Corporation", " Incorporated", " Holdings", " Company", " Corp.",
    " Corp", " Inc.", " Inc", " Co.", " plc", " N.V.", " S.A.", " Ltd.",
    " Limited", " Group",
]

# Words that are also ordinary English (or extremely generic finance/geo)
# vocabulary -- never add these as a STANDALONE single-word alias, even if
# suffix-stripping would produce them. The full un-stripped name is still
# added, so recall isn't lost entirely, only the risky short form.
COMMON_WORD_BLOCKLIST = {
    "target", "visa", "gap", "general", "american", "united", "national",
    "global", "public", "home", "first", "best", "west", "east", "north",
    "south", "group", "capital", "real", "growth", "value", "core",
    "access", "block", "square", "pure", "snap", "meta", "now", "air",
    "key", "keys", "match", "fair", "cash", "church", "comfort", "crown",
    "dow", "expedia", "extra", "federal", "fortive", "fortinet", "garmin",
    "genuine", "globe", "hasbro", "hess", "host", "humana", "hunt",
    "incyte", "insight", "intuit", "iron", "jabil", "jack", "kroger",
    "live", "marathon", "martin", "masco", "matter", "medtronic", "mid",
    "mohawk", "moody", "mosaic", "motorola", "nasdaq", "netapp", "news",
    "nike", "old", "omnicom", "on", "otis", "packaging", "paramount",
    "parker", "paychex", "paypal", "pentair", "people", "pfizer", "pool",
    "principal", "prologis", "quanta", "raymond", "regency", "regions",
    "robert", "rollins", "roper", "ross", "royal", "salesforce", "schwab",
    "sempra", "service", "simon", "skyworks", "smith", "smucker", "solar",
    "southern", "stanley", "starbucks", "state", "steel", "steris",
    "stryker", "sysco", "tapestry", "tesla", "texas", "the", "thermo",
    "travelers", "trimble", "truist", "tyson", "ulta", "union",
    "universal", "valero", "ventas", "verisign", "vertex", "viatris",
    "vulcan", "walgreens", "walmart", "warner", "waste", "waters", "wells",
    "western", "weyerhaeuser", "whirlpool", "williams", "willis", "yum",
    "zebra", "zimmer", "zoetis", "gild", "snow", "es", "et", "gen", "one",
    "all", "day", "digital", "direct", "edge", "elite", "equity",
    "essential", "fast", "fine", "five", "flex", "floor", "focus", "ford",
}

# Common ADRs likely to come up in macro/allocation podcast discussion but
# absent from a US-domestic S&P 500 constituents list. Small and hand-
# curated deliberately -- the 500-entry bulk above is what must not be
# hand-typed, not this ~25-line supplement.
COMMON_ADR_ALIASES = {
    "BABA": ["Alibaba"],
    "TSM": ["TSMC", "Taiwan Semiconductor"],
    "ASML": ["ASML"],
    "NVO": ["Novo Nordisk"],
    "SAP": ["SAP"],
    "TM": ["Toyota"],
    "SONY": ["Sony"],
    "BUD": ["Anheuser-Busch InBev", "AB InBev"],
    "UL": ["Unilever"],
    "RIO": ["Rio Tinto"],
    "BHP": ["BHP Group", "BHP Billiton"],
    "SHEL": ["Shell"],
    "TTE": ["TotalEnergies"],
    "HSBC": ["HSBC"],
    "BTI": ["British American Tobacco"],
    "DEO": ["Diageo"],
    "NVS": ["Novartis"],
    "AZN": ["AstraZeneca"],
    "GSK": ["GSK", "GlaxoSmithKline"],
    "PDD": ["Pinduoduo", "Temu"],
    "JD": ["JD.com"],
    "NTES": ["NetEase"],
    "BIDU": ["Baidu"],
    "INFY": ["Infosys"],
    "STLA": ["Stellantis"],
    "MUFG": ["Mitsubishi UFJ"],
}


def _clean_security_name(name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name)  # drop "(Class A)", "(The)", etc.
    return re.sub(r"\s+", " ", name).strip()


def _derive_aliases(security_name: str) -> list[str]:
    clean = _clean_security_name(security_name)
    aliases = [clean]
    for suffix in STRIPPABLE_SUFFIXES:
        if clean.endswith(suffix):
            short = clean[: -len(suffix)].strip().rstrip("&,.").strip()
            if short and short.lower() not in COMMON_WORD_BLOCKLIST:
                aliases.append(short)
            break
    return aliases


def fetch_sp500_rows() -> list[dict]:
    req = urllib.request.Request(SP500_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(data)))


def main():
    if os.path.exists(ALIASES_PATH):
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = {}
    existing = {k: v for k, v in existing.items() if not k.startswith("_")}
    before_count = len(existing)

    rows = fetch_sp500_rows()
    print("Fetched %d S&P 500 constituent rows." % len(rows))

    merged = {k: list(v) for k, v in existing.items()}
    added_tickers = 0
    for row in rows:
        ticker = row["Symbol"].strip().upper()
        derived = _derive_aliases(row["Security"])
        if ticker not in merged:
            merged[ticker] = derived
            added_tickers += 1
        else:
            for alias in derived:
                if alias not in merged[ticker]:
                    merged[ticker].append(alias)

    for ticker, aliases in COMMON_ADR_ALIASES.items():
        if ticker not in merged:
            merged[ticker] = list(aliases)
            added_tickers += 1
        else:
            for alias in aliases:
                if alias not in merged[ticker]:
                    merged[ticker].append(alias)

    output = {
        "_comment": (
            "ticker -> [alias strings] for utils/moment_windows.py ticker-proximity "
            "matching. Generated by scripts/generate_ticker_aliases.py from the S&P 500 "
            "constituents dataset + a small hand-curated ADR supplement, merged with "
            "pre-existing hand-curated entries for held positions (never overwritten, "
            "only added to). Re-run the generator to refresh; do not hand-edit the bulk "
            "S&P 500 entries. Transcripts are lowercase auto-captions, so hosts say "
            "company names ('Nvidia'), not tickers ('NVDA') -- company-name aliases are "
            "the primary signal. Single-word aliases that collide with ordinary English "
            "words are deliberately omitted (see COMMON_WORD_BLOCKLIST in the generator) "
            "-- the full company name is kept instead."
        ),
        **dict(sorted(merged.items())),
    }

    with open(ALIASES_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, indent=2)

    after_count = len(merged)
    print("Tickers before: %d" % before_count)
    print("Tickers after:  %d" % after_count)
    print("Newly added:    %d" % added_tickers)
    print("Wrote %s" % ALIASES_PATH)


if __name__ == "__main__":
    main()

"""
Frozen routine registry for desk launcher.

Browser posts a registry id + typed args; argv is assembled server-side.
Never accept raw command strings from the client.

Launch policy (2026-08-28 amendment): the UI may launch routines that write
regenerable computed surfaces or Bill's own authored input; broker-derived
mutations and promotion to authoritative surfaces stay CLI-only. See CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Routines approved for UI launch with --live (amendment 2026-08-28).
UI_APPROVED_LIVE_IDS = frozenset({
    "store-backup-live",
    "corpus-index-live",
    "ingest-precommitments-live",
    "refresh-dashboard-live",
    "tax-refresh-live",
})


@dataclass(frozen=True)
class ArgSpec:
    name: str
    kind: str  # ticker | shares | float | str | int | query
    required: bool = False
    default: str | None = None
    label: str = ""


@dataclass(frozen=True)
class Routine:
    id: str
    label: str
    argv: tuple[str, ...]
    tier: int  # 0 read-only/sandbox | 1 UI-approved write
    description: str
    args: tuple[ArgSpec, ...] = ()
    timeout_sec: int = 300
    long_run_warning: str | None = None
    group: str = "SYSTEM"
    writes_banner: str = ""
    confirm_name: bool = False


def _routine(
    rid: str,
    label: str,
    argv: tuple[str, ...],
    tier: int,
    description: str,
    *,
    args: tuple[ArgSpec, ...] = (),
    timeout_sec: int = 300,
    long_run_warning: str | None = None,
    group: str = "SYSTEM",
    writes_banner: str = "",
    confirm_name: bool = False,
) -> Routine:
    return Routine(
        id=rid,
        label=label,
        argv=argv,
        tier=tier,
        description=description,
        args=args,
        timeout_sec=timeout_sec,
        long_run_warning=long_run_warning,
        group=group,
        writes_banner=writes_banner,
        confirm_name=confirm_name,
    )


ROUTINES: dict[str, Routine] = {}


def _reg(r: Routine) -> None:
    ROUTINES[r.id] = r


# --- Tier 0: read-only / sandbox ---

_reg(_routine(
    "judge-rotations",
    "Judgment — rotations",
    ("manager.py", "judge", "rotations"),
    0,
    "Unit A rotation quality aggregates (Rotation_Review).",
    group="REVIEW",
))
_reg(_routine(
    "judge-lifecycle",
    "Judgment — lifecycle (ticker)",
    ("manager.py", "judge", "lifecycle"),
    0,
    "Unit B lifecycle campaign for one ticker.",
    args=(ArgSpec("ticker", "ticker", required=True, label="Ticker"),),
    timeout_sec=600,
    group="REVIEW",
))
_reg(_routine(
    "judge-lifecycle-all",
    "Judgment — lifecycle (all)",
    ("manager.py", "judge", "lifecycle", "--all"),
    0,
    "Unit B summary for every held ticker.",
    timeout_sec=7200,
    long_run_warning="Runs ~2–3 min per ticker (~90 min for the full book).",
    group="REVIEW",
))
_reg(_routine(
    "judge-lifecycle-missing-json",
    "Judgment — backfill missing sidecars (dry run)",
    ("manager.py", "judge", "lifecycle", "--missing-json"),
    0,
    "Lists lifecycle artifacts with no JSON sidecar. Recompute is CLI-only (--live).",
    timeout_sec=120,
    group="REVIEW",
))
_reg(_routine(
    "judge-calibration",
    "Judgment — calibration",
    ("manager.py", "judge", "calibration"),
    0,
    "Unit C calibration scaffold.",
    group="REVIEW",
))
_reg(_routine(
    "tax-project",
    "Tax projection",
    ("manager.py", "tax", "project"),
    0,
    "Pre-trade tax surface (ESTIMATE only).",
    args=(
        ArgSpec("ticker", "ticker", required=True, label="Ticker"),
        ArgSpec("shares", "shares", required=False, label="Shares to trim"),
    ),
    group="DECIDE",
))
_reg(_routine(
    "corpus-status",
    "Corpus status",
    ("manager.py", "corpus", "status"),
    0,
    "FTS index document counts.",
    group="DESK",
))
_reg(_routine(
    "corpus-search",
    "Corpus search",
    ("manager.py", "corpus", "search"),
    0,
    "Search vault / transcripts / digests.",
    args=(ArgSpec("query", "query", required=True, label="Query"),),
    group="DESK",
))
_reg(_routine(
    "store-evidence-status",
    "Evidence status",
    ("manager.py", "store", "evidence-status"),
    0,
    "Accrual gate and evidence table counts.",
    group="SYSTEM",
))
_reg(_routine(
    "store-verify",
    "Store verify",
    ("manager.py", "store", "verify"),
    0,
    "Ledger fingerprint verify.",
    group="SYSTEM",
))
_reg(_routine(
    "store-bundle-parity",
    "Bundle parity",
    ("manager.py", "store", "bundle-parity"),
    0,
    "Sheets vs SQLite fingerprint diff.",
    group="SYSTEM",
))
_reg(_routine(
    "store-provenance",
    "Store provenance",
    ("manager.py", "store", "provenance"),
    0,
    "Data-class regenerability table.",
    group="SYSTEM",
))
_reg(_routine(
    "journal-precommit-list",
    "Pre-commitments — list",
    ("manager.py", "journal", "precommit", "--list"),
    0,
    "List declared precommitments.",
    group="DECIDE",
))
_reg(_routine(
    "journal-precommit-pending",
    "Pre-commitments — pending",
    ("manager.py", "journal", "precommit", "--pending"),
    0,
    "Pending firings awaiting response.",
    group="DECIDE",
))
_reg(_routine(
    "journal-reconcile",
    "Journal reconcile (dry)",
    ("manager.py", "journal", "reconcile"),
    0,
    "Rationale loop batch triage — dry run only.",
    timeout_sec=600,
    group="DECIDE",
))
_reg(_routine(
    "probe-price-history",
    "Probe — price history",
    ("manager.py", "probe", "price-history"),
    0,
    "Schwab OHLCV bars (read-only).",
    args=(
        ArgSpec("ticker", "ticker", required=True, label="Ticker"),
        ArgSpec("days", "int", required=False, default="365", label="Days"),
    ),
    group="SYSTEM",
))
_reg(_routine(
    "probe-fundamentals",
    "Probe — fundamentals",
    ("manager.py", "probe", "fundamentals"),
    0,
    "Schwab instrument fundamentals dump.",
    args=(ArgSpec("ticker", "ticker", required=True, label="Ticker"),),
    group="SYSTEM",
))
_reg(_routine(
    "probe-market-hours",
    "Probe — market hours",
    ("manager.py", "probe", "market-hours"),
    0,
    "Market hours probe.",
    group="SYSTEM",
))
_reg(_routine(
    "probe-reconcile",
    "Probe — reconcile",
    ("manager.py", "probe", "reconcile"),
    0,
    "Position reconcile probe.",
    group="SYSTEM",
))
_reg(_routine(
    "probe-price-source-stats",
    "Probe — price source stats",
    ("manager.py", "probe", "price-source-stats"),
    0,
    "Price history source statistics.",
    group="SYSTEM",
))

# --- Tier 1: UI-approved writes (amendment 2026-08-28) ---

_reg(_routine(
    "store-backup-live",
    "Store backup",
    ("manager.py", "store", "backup", "--live"),
    1,
    "VACUUM INTO snapshot + SHA-256 sidecar (+ Drive copy if configured).",
    writes_banner="Writes: data/portfolio_store_backups/ (additive SQLite snapshot)",
    timeout_sec=600,
    group="SYSTEM",
))
_reg(_routine(
    "corpus-index-live",
    "Corpus index",
    ("manager.py", "corpus", "index", "--live"),
    1,
    "Incremental FTS index from files on disk.",
    writes_banner="Writes: SQLite corpus_docs / corpus_chunks / corpus_fts (regenerable local index)",
    timeout_sec=900,
    group="DESK",
))
_reg(_routine(
    "ingest-precommitments-live",
    "Ingest precommitments",
    ("manager.py", "journal", "ingest-precommitments", "--live"),
    1,
    "Move your Precommitments tab declarations into SQLite (append-and-mark).",
    writes_banner="Writes: SQLite precommitments + Precommitments tab Ingested_At marks (your authored input)",
    timeout_sec=300,
    group="DECIDE",
))
_reg(_routine(
    "refresh-dashboard-live",
    "Refresh dashboard",
    ("manager.py", "refresh", "dashboard", "--live"),
    1,
    "Clear-and-rebuild computed dashboard tabs from ledger data.",
    writes_banner="Writes: Sheets 0_DASHBOARD, Decision_View, Valuation_Card (+ conditional formatting)",
    confirm_name=True,
    timeout_sec=900,
    group="DAILY",
))
_reg(_routine(
    "tax-refresh-live",
    "Tax refresh",
    ("manager.py", "tax", "refresh", "--live"),
    1,
    "Rebuild Tax_Control from ledger (computed surface).",
    writes_banner="Writes: Sheets Tax_Control + SQLite tax_control mirror",
    confirm_name=True,
    timeout_sec=600,
    group="DECIDE",
))

LAUNCHABLE_ROUTINES = {k: v for k, v in ROUTINES.items() if v.tier in (0, 1)}
TIER0_ROUTINES = {k: v for k, v in ROUTINES.items() if v.tier == 0}


def routine_by_id(routine_id: str) -> Routine | None:
    return ROUTINES.get(routine_id)


def is_ui_launchable(routine_id: str) -> bool:
    r = routine_by_id(routine_id)
    return r is not None and r.tier in (0, 1)


def validate_routine_args(routine: Routine, raw: dict[str, Any]) -> dict[str, str]:
    """Validate and normalize args; raises ValueError on rejection."""
    import re

    out: dict[str, str] = {}
    ticker_re = re.compile(r"^[A-Z0-9.\-]{1,8}$")
    for spec in routine.args:
        val = raw.get(spec.name)
        if val is None or (isinstance(val, str) and not val.strip()):
            if spec.required:
                raise ValueError(f"Missing required arg: {spec.name}")
            if spec.default is not None:
                out[spec.name] = spec.default
            continue
        s = str(val).strip()
        if spec.kind == "ticker":
            t = s.upper()
            if not ticker_re.match(t) or ".." in t or "/" in t or "\\" in t:
                raise ValueError(f"Invalid ticker: {s!r}")
            out[spec.name] = t
        elif spec.kind == "shares":
            try:
                f = float(s)
            except ValueError as e:
                raise ValueError(f"Invalid shares: {s!r}") from e
            if f <= 0 or f > 1_000_000:
                raise ValueError(f"Shares out of range: {f}")
            out[spec.name] = str(f)
        elif spec.kind == "int":
            try:
                n = int(float(s))
            except ValueError as e:
                raise ValueError(f"Invalid integer: {s!r}") from e
            if n < 1 or n > 5000:
                raise ValueError(f"Integer out of range: {n}")
            out[spec.name] = str(n)
        elif spec.kind == "query":
            if len(s) > 500 or ";" in s or "\n" in s:
                raise ValueError("Invalid query string")
            out[spec.name] = s
        else:
            if len(s) > 200:
                raise ValueError(f"Arg too long: {spec.name}")
            out[spec.name] = s
    return out


def build_argv(routine: Routine, args: dict[str, str]) -> list[str]:
    """Assemble argv from frozen tuple + validated positional/flag args."""
    argv = list(routine.argv)
    if routine.id == "tax-project":
        argv.extend(["--ticker", args["ticker"]])
        if args.get("shares"):
            argv.extend(["--shares", args["shares"]])
    elif routine.id == "judge-lifecycle":
        argv.extend(["--ticker", args["ticker"]])
    elif routine.id == "corpus-search":
        argv.append(args["query"])
    elif routine.id == "probe-price-history":
        argv.append(args["ticker"])
        if args.get("days"):
            argv.extend(["--days", args["days"]])
    elif routine.id == "probe-fundamentals":
        argv.append(args["ticker"])
    return argv


DURATION_HINTS: dict[str, str] = {
    "judge-lifecycle": "~3 min",
    "judge-lifecycle-all": "~90 min",
    "judge-rotations": "~30 sec",
    "judge-calibration": "~15 sec",
    "corpus-index-live": "~1 min",
    "refresh-dashboard-live": "~2 min",
    "tax-refresh-live": "~3 min",
    "store-backup-live": "~30 sec",
}


def routine_duration_hint(routine: Routine) -> str:
    return DURATION_HINTS.get(routine.id, f"≤{max(1, routine.timeout_sec // 60)} min")

# CLI Migration Phase 4 — Schwab API as a Bundle Data Source
# Target: Claude Code or Gemini CLI 3 Pro
# Prerequisite: Phase 3 committed and green. Re-Buy Analyst producing
# calibrated output against UNH on the CSV-sourced bundle path.

## Overview

**This phase is smaller than it sounds.** The Schwab API integration was
actually completed during "Phase 5-S" in April 2026 — before the CLI
migration started. The following already exist in the repo and are live:

- `utils/schwab_client.py` — read-only scoped clients (Accounts + Market Data)
- `utils/schwab_token_store.py` — GCS-backed OAuth token persistence
- `cloud_functions/token_refresh/` — 25-min keep-alive Cloud Function
- `scripts/schwab_initial_auth.py` and `scripts/schwab_manual_reauth.py`
- `fetch_positions(client)` returning a snake_case DataFrame with
  nuclear type enforcement on numeric columns
- Post-integration bug fixes (cash aggregation, price masking, description
  backfill) from the 2026-04-10 patch

What Phase 4 actually needs to do is **wire the existing Schwab client
into `core/bundle.py` as a pluggable data source**, alongside the CSV
path that Phase 1 built. The bundle interface does not change — only
the source of positions and prices changes. Every agent downstream
(Re-Buy Analyst from Phase 3, the three agents coming in Phase 5)
continues to work unchanged because they consume the bundle, not the
data source.

**Do not rebuild the Schwab client. Do not touch the Cloud Function.
Do not re-run OAuth setup. Read the existing modules and wire them in.**

## What Phase 4 produces

- `build_bundle()` in `core/bundle.py` gains a `source` parameter:
  `"schwab"` (default when Schwab client is available),
  `"csv"` (explicit CSV path), or
  `"auto"` (try Schwab, fall back to CSV on any failure).
- `manager.py snapshot` gains a `--source` flag and makes `--csv` optional.
- Bundle records a new field `data_source` documenting which path produced it.
- `price_source` values extend from the Phase 1b vocabulary to include
  `"schwab_quote"` (live Schwab Market Data quote), keeping the audit
  trail for every position price.
- Tax treatment per position: each row gains a `tax_treatment` field
  derived from the Schwab account type (`taxable | ira | roth | hsa`).
  The CSV path sets this to `"unknown"` for now.
- A `data_source_fingerprint` field on the bundle payload captures a
  short hash of the upstream source identity (CSV file SHA for CSV
  path, concatenated account hashes for Schwab path) so bundles can
  be compared across runs without pulling the full payload.

## What Phase 4 explicitly does NOT do

- **No changes to `utils/schwab_client.py` or `utils/schwab_token_store.py`.**
  These are battle-tested against a live $545K portfolio. They stay as-is.
- **No changes to the Cloud Function.** It's running and refreshing tokens
  on a 25-minute cadence. Leave it alone.
- **No new OAuth setup.** Tokens are already in GCS.
- **No options chain endpoint.** That's Phase 8a.
- **No trading endpoints, ever.** The existing safety preamble and grep
  checks in `schwab_client.py` stay in place. This phase adds zero new
  Schwab method calls beyond what `fetch_positions()` and quote lookup
  already use.
- **No deletion of the CSV path.** CSV is preserved as `--source csv`
  and as the `auto` mode's fallback. Disaster recovery matters.
- **No retirement of `app.py`.** That's Phase 7.

## Key Design Decisions

1. **The bundle interface is source-agnostic.** `build_bundle()` produces
   the same ContextBundle dataclass shape regardless of source. Agents
   downstream see no difference. This is the whole reason Phase 1
   designed the bundle the way it did.

2. **`auto` mode is the new default when Schwab client is reachable.**
   If `get_accounts_client()` returns a non-None client, `auto` uses
   Schwab. If it returns None (missing token, auth failure, GCS
   unreachable), `auto` falls back to CSV with a loud console warning
   and an entry in `enrichment_errors`.

3. **CSV path requires explicit `--csv` + `--source csv`.** No more
   guessing. If you pass `--source csv`, you must provide `--csv PATH`.
   If you pass `--source schwab`, `--csv` is ignored if present.
   If you pass `--source auto` (or omit `--source`), the CLI picks
   Schwab if available and CSV if a `--csv` path is provided as a
   fallback hint.

4. **Schwab path does NOT re-enrich with yfinance by default.** The
   Schwab Market Data API already returns live quotes via
   `fetch_positions()`. Running yfinance on top is redundant and slow.
   However, if `fetch_positions()` returns a zero price for any row
   (the 2026-04-10 bug patch), that row gets yfinance fallback
   enrichment specifically — same logic that was added to `app.py`
   during the integration. Add this to a helper function in
   `core/bundle.py`, not inline.

5. **Tax treatment comes from the Schwab account type.** Schwab's
   account type field maps cleanly:
   - `CASH` or `MARGIN` → `"taxable"`
   - `IRA` → `"ira"`
   - `ROTH_IRA` → `"roth"`
   - `HSA` → `"hsa"`
   - Anything else → `"unknown"`
   Store this on each position row. Phase 5+ agents (tax-loss
   harvesting especially) will consume it.

6. **`data_source_fingerprint` is stable across runs with the same
   inputs.** For CSV, it's the SHA256 of the raw CSV bytes (already
   computed as `source_csv_sha256` — just renamed/added). For Schwab,
   it's `sha256(sorted_account_hashes).hexdigest()[:16]`. Two
   snapshots from the same source on the same day should share the
   same fingerprint even though their bundle hashes differ (because
   bundle hash includes the timestamp and prices).

7. **Existing bundle_hash contract is unchanged.** The bundle_hash
   still hashes the canonical payload minus the hash field itself.
   New fields (`data_source`, `tax_treatment`, etc.) become part of
   the hashable payload. The Phase 1b `_hashable_payload` helper
   continues to be the single source of truth.

8. **Multi-account aggregation is already handled.** The 2026-04-10
   patch already fixed `fetch_positions()` to read
   `currentBalances.cashBalance` from every account and append a
   unified CASH_MANUAL row. Phase 4 does not re-aggregate — it
   trusts `fetch_positions()` and builds the bundle around whatever
   it returns.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] Phase 3 is committed and green
- [ ] `utils/schwab_client.py` exists and exports `get_accounts_client()`,
      `get_market_client()`, and `fetch_positions(client)`
- [ ] `utils/schwab_token_store.py` exists and the token file on GCS is
      current (verify with: `gsutil ls gs://portfolio-manager-tokens/`)
- [ ] The Cloud Function is running on schedule (verify with:
      `gcloud functions describe token_refresh --region us-central1`)
- [ ] `fetch_positions()` returns a non-empty DataFrame when called
      with a live client. Test from a Python REPL:
      ```python
      from utils.schwab_client import get_accounts_client, fetch_positions
      df = fetch_positions(get_accounts_client())
      print(len(df), "positions")
      ```
- [ ] `core/bundle.py` still round-trips cleanly on the CSV path
- [ ] At least one successful `manager.py snapshot --csv ...` run in the
      last 7 days (sanity check that the CSV path is still live)

If any of the above fail, STOP and fix before starting Phase 4. Do
not try to work around a broken Schwab client from inside `core/bundle.py`.

---

## Prompt 1 of 6: Audit the existing Schwab modules

```text
Read these files fully before making any changes. Do not modify them.

1. utils/schwab_client.py
2. utils/schwab_token_store.py
3. cloud_functions/token_refresh/main.py (for reference only — do not touch)
4. scripts/schwab_initial_auth.py (for reference only — do not touch)
5. core/bundle.py (current Phase 1b state)
6. manager.py (current snapshot subcommand)

After reading, produce a short written audit covering:

a) The exact signature of `get_accounts_client()`. Does it return
   `schwab.client.Client | None` or some other shape? What does it
   return when the token is missing or auth fails?

b) The exact signature of `fetch_positions(client)`. What DataFrame
   columns does it return? What does it do with the CASH_MANUAL row?
   Are all numeric columns already cast to float64 by the nuclear
   type enforcement the 2026-04-10 patch added?

c) The exact signature of `get_market_client()` and whether it has
   a method for fetching individual quotes (needed for yfinance
   fallback replacement — if Schwab can provide the zero-price
   fallback itself, prefer that over yfinance).

d) How the current `build_bundle()` in `core/bundle.py` walks its
   input — specifically, the exact call signature for the CSV parser
   and which DataFrame columns it expects post-parse.

e) Whether `schwab_client.fetch_positions()` returns a `tax_treatment`
   or similar account-type field per row. If not, what Schwab API
   response field carries the account type (it's usually
   `securitiesAccount.type` on the account-level response, not the
   position row) — and is the current `fetch_positions()` preserving
   this info or dropping it?

f) Any place the 2026-04-10 bug patches live in app.py that will NOT
   carry over to the CLI path — specifically the zero-price masking
   and description backfill. These patches need to be either hoisted
   into a shared helper or re-implemented in core/bundle.py for the
   Schwab path.

Output this audit as a markdown block in the chat BEFORE touching any
file. Bill needs to see the audit and confirm before implementation
proceeds. Do not proceed to Prompt 2 until Bill approves the audit.
```

**This audit step is not optional. The whole value of Phase 4 depends
on building on top of the existing Schwab integration rather than
around it. Missing a detail here would mean duplicating code or
introducing subtle divergence between the CLI path and the Streamlit
path. Force the audit to happen explicitly.**

---

## Prompt 2 of 6: Extend core/bundle.py with pluggable data sources

```text
Read the audit output from Prompt 1 before making any changes. If any
detail from the audit contradicts what this prompt assumes, stop and
ask Bill for clarification rather than guessing.

=== EDIT 1: Add a source enum constant ===

Add to core/bundle.py near the top, after the existing constants:

    # Data source modes for build_bundle()
    SOURCE_SCHWAB = "schwab"
    SOURCE_CSV = "csv"
    SOURCE_AUTO = "auto"
    VALID_SOURCES = {SOURCE_SCHWAB, SOURCE_CSV, SOURCE_AUTO}

=== EDIT 2: Extend the ContextBundle dataclass ===

Add four new fields to the ContextBundle dataclass (preserve all
existing fields exactly):

    data_source: str                    # "schwab" | "csv"
    data_source_fingerprint: str        # stable identity of the source
    tax_treatment_available: bool       # True only on Schwab path in v1

Note: per-position tax_treatment is stored INSIDE each position dict
in the existing `positions` list field, not as a top-level dataclass
field. The dataclass-level bool just signals whether the field is
meaningfully populated across the bundle.

=== EDIT 3: Add a Schwab-source builder function ===

Add a new function to core/bundle.py:

    def _build_from_schwab(
        cash_manual: float,
    ) -> tuple[pd.DataFrame, str, list[str]]:
        '''
        Fetch positions from the live Schwab API.

        Returns:
            (positions_df, data_source_fingerprint, enrichment_errors)

        Raises:
            RuntimeError: if get_accounts_client() returns None (no token,
                auth failure, GCS unreachable) — the caller decides
                whether to fall back to CSV.
        '''
        # Lazy import so core/bundle.py is importable even on machines
        # without schwab-py installed (unit tests, CI).
        try:
            from utils.schwab_client import get_accounts_client, fetch_positions
        except ImportError as e:
            raise RuntimeError(
                f"Schwab client not available: {e}. "
                "Install schwab-py or use --source csv."
            )

        client = get_accounts_client()
        if client is None:
            raise RuntimeError(
                "Schwab accounts client returned None — token missing, "
                "expired, or GCS unreachable. Check "
                "`gsutil ls gs://portfolio-manager-tokens/` and "
                "the Cloud Function logs. Fall back to --source csv "
                "or run scripts/schwab_manual_reauth.py."
            )

        df = fetch_positions(client)
        if df is None or df.empty:
            raise RuntimeError(
                "fetch_positions() returned empty. Check Schwab API "
                "availability and verify the account hash in secrets.toml."
            )

        enrichment_errors: list[str] = []

        # Mark every row with price_source="schwab_quote" unless the
        # 2026-04-10 zero-price patch fires (handled below)
        df["price_source"] = "schwab_quote"

        # Zero-price fallback: any position where Schwab returned 0
        # gets yfinance enrichment. This matches the app.py fix from
        # the 2026-04-10 bug patches.
        zero_price_mask = df["price"] <= 0
        if zero_price_mask.any():
            zero_tickers = df.loc[zero_price_mask, "ticker"].tolist()
            logger_warning = (
                f"{len(zero_tickers)} position(s) returned zero price "
                f"from Schwab; falling back to yfinance: {zero_tickers}"
            )
            enrichment_errors.append(logger_warning)
            for idx in df.index[zero_price_mask]:
                ticker = df.at[idx, "ticker"]
                if ticker in CASH_TICKERS:
                    continue
                try:
                    import yfinance
                    yt = yfinance.Ticker(ticker)
                    try:
                        price = yt.fast_info["lastPrice"]
                    except (AttributeError, KeyError, Exception):
                        hist = yt.history(period="1d")
                        if hist.empty:
                            raise ValueError(f"No yfinance data for {ticker}")
                        price = hist["Close"].iloc[-1]
                    df.at[idx, "price"] = float(price)
                    df.at[idx, "price_source"] = "yfinance_live"
                    # Recompute market_value with the fallback price
                    df.at[idx, "market_value"] = (
                        float(df.at[idx, "quantity"]) * float(price)
                    )
                except Exception as e:
                    enrichment_errors.append(
                        f"Zero-price fallback failed for {ticker}: {e}"
                    )

        # Tax treatment per position. If fetch_positions() already
        # populates a tax_treatment column, trust it. Otherwise default
        # to "unknown" and log. (The exact column name should come from
        # the audit in Prompt 1 — adjust if needed.)
        if "tax_treatment" not in df.columns:
            df["tax_treatment"] = "unknown"
            enrichment_errors.append(
                "Schwab fetch_positions did not return tax_treatment — "
                "all positions marked 'unknown'. Extend fetch_positions "
                "in a follow-up if tax-loss harvesting needs this."
            )

        # Always inject the synthetic CASH_MANUAL row for schema
        # consistency, same as CSV path. If fetch_positions already
        # returned a CASH_MANUAL row (the 2026-04-10 cash aggregation
        # patch), skip the injection — don't duplicate.
        if not (df["ticker"] == "CASH_MANUAL").any():
            cash_row = {
                "ticker": "CASH_MANUAL",
                "description": "Manual Cash Entry",
                "quantity": float(cash_manual),
                "price": 1.0,
                "market_value": float(cash_manual),
                "cost_basis": float(cash_manual),
                "asset_class": "Cash",
                "asset_strategy": "Cash",
                "is_cash": True,
                "price_source": "manual",
                "tax_treatment": "taxable",
            }
            df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

        # Compute data_source_fingerprint from account hash(es).
        # For MVP, use the single SCHWAB_ACCOUNT_HASH from config.
        import hashlib
        import config as _config
        account_hash = getattr(_config, "SCHWAB_ACCOUNT_HASH", "")
        source_fingerprint = hashlib.sha256(
            account_hash.encode("utf-8")
        ).hexdigest()[:16]

        return df, source_fingerprint, enrichment_errors

=== EDIT 4: Refactor the existing CSV path into a helper ===

Extract the existing CSV-reading logic in build_bundle() into a helper:

    def _build_from_csv(
        csv_path: Path,
        cash_manual: float,
    ) -> tuple[pd.DataFrame, str, list[str]]:
        '''
        Parse a Schwab CSV export into the same DataFrame shape as
        _build_from_schwab(). Used for disaster recovery and for users
        without Schwab API access.
        '''
        # Keep the EXISTING csv parsing + yfinance enrichment + cash
        # injection logic exactly as it was in Phase 1b. Return the
        # resulting (df, csv_sha256, enrichment_errors) tuple. Every
        # row gets tax_treatment="unknown" on the CSV path.
        # ... (move the existing logic here unchanged, with minimal
        #      tweaks to match the new return signature)
        # Make sure every position row has a price_source field
        # (yfinance_live or csv_fallback) and tax_treatment="unknown"
        ...

=== EDIT 5: Rewrite build_bundle() as a dispatcher ===

Replace the body of build_bundle() with a dispatcher:

    def build_bundle(
        source: str = SOURCE_AUTO,
        csv_path: Path | None = None,
        cash_manual: float = 0.0,
    ) -> ContextBundle:
        '''
        Build an immutable context bundle from the requested data source.

        Args:
            source: "schwab" | "csv" | "auto" (default)
            csv_path: required if source == "csv" or as fallback for "auto"
            cash_manual: manual cash balance (used if source doesn't
                provide one itself)

        Raises:
            ValueError: on invalid source or missing csv_path when required
            RuntimeError: on source-specific failure with no fallback available
        '''
        if source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}'. Must be one of {VALID_SOURCES}."
            )

        if source == SOURCE_CSV:
            if csv_path is None:
                raise ValueError(
                    "source='csv' requires csv_path. "
                    "Pass --csv PATH or use --source auto."
                )
            df, source_fingerprint, enrichment_errors = _build_from_csv(
                csv_path=csv_path, cash_manual=cash_manual
            )
            resolved_source = SOURCE_CSV
            source_path_repr = str(csv_path)

        elif source == SOURCE_SCHWAB:
            df, source_fingerprint, enrichment_errors = _build_from_schwab(
                cash_manual=cash_manual
            )
            resolved_source = SOURCE_SCHWAB
            source_path_repr = "schwab_api"

        elif source == SOURCE_AUTO:
            try:
                df, source_fingerprint, enrichment_errors = (
                    _build_from_schwab(cash_manual=cash_manual)
                )
                resolved_source = SOURCE_SCHWAB
                source_path_repr = "schwab_api"
            except RuntimeError as schwab_err:
                if csv_path is None:
                    raise RuntimeError(
                        f"Schwab source failed and no csv_path provided "
                        f"as fallback. Schwab error: {schwab_err}. "
                        f"Either provide --csv PATH or debug the Schwab "
                        f"client."
                    )
                # Fall back to CSV with a loud warning
                enrichment_errors = [
                    f"Schwab source failed — fell back to CSV. "
                    f"Schwab error: {schwab_err}"
                ]
                df2, source_fingerprint, csv_errors = _build_from_csv(
                    csv_path=csv_path, cash_manual=cash_manual
                )
                df = df2
                enrichment_errors.extend(csv_errors)
                resolved_source = SOURCE_CSV
                source_path_repr = str(csv_path)
        else:
            raise ValueError(f"Unreachable source branch: {source}")

        # From here, the logic is shared across all sources:
        # normalize positions, compute totals, build payload, hash it,
        # return the ContextBundle. The Phase 1b normalization and
        # hashing logic stays exactly as it was — only the new fields
        # get added to the payload.

        # Compute totals
        df["market_value"] = df["quantity"] * df["price"]
        total_value = float(df["market_value"].sum())
        position_count = len(df)
        if total_value > 0:
            df["weight_pct"] = (df["market_value"] / total_value) * 100
        else:
            df["weight_pct"] = 0.0

        positions = _normalize_positions(df.to_dict(orient="records"))
        tax_treatment_available = any(
            p.get("tax_treatment", "unknown") != "unknown"
            for p in positions
        )

        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "timestamp_utc": timestamp_utc,
            "source_csv_path": source_path_repr,  # renamed meaning: "source identity"
            "source_csv_sha256": source_fingerprint,  # renamed meaning: "source fingerprint"
            "data_source": resolved_source,
            "data_source_fingerprint": source_fingerprint,
            "tax_treatment_available": tax_treatment_available,
            "positions": positions,
            "cash_manual": float(cash_manual),
            "total_value": total_value,
            "position_count": int(position_count),
            "environment": _capture_environment(),
            "enrichment_errors": enrichment_errors,
        }

        bundle_hash = _sha256_canonical(_hashable_payload(payload))

        return ContextBundle(
            bundle_hash=bundle_hash,
            **payload,
        )

IMPORTANT: the fields `source_csv_path` and `source_csv_sha256` are
intentionally kept as-is (same names) for backward compatibility with
any bundles already on disk. Their SEMANTICS broaden: they now mean
"source identity" and "source fingerprint" regardless of whether the
source was CSV or Schwab. The existing load_bundle() continues to
work on old bundles because the fields exist with the same names.
Add a docstring comment explaining this.

Do NOT:
- Remove or modify _hashable_payload, _normalize_positions,
  _sha256_file, or _sha256_canonical
- Change the bundle_hash computation contract
- Delete the CSV path
- Import schwab-py at module top-level — lazy import only
- Inline yfinance enrichment in build_bundle itself — keep it inside
  _build_from_schwab and _build_from_csv
```

---

## Prompt 3 of 6: Update manager.py snapshot subcommand

```text
Read manager.py before making changes. The current snapshot subcommand
takes --csv as required and --cash as optional.

Update the snapshot subcommand signature:

    @app.command()
    def snapshot(
        source: str = typer.Option(
            "auto", "--source",
            help="Data source: 'schwab', 'csv', or 'auto' (default). "
                 "'auto' tries Schwab first and falls back to CSV if "
                 "--csv is provided."
        ),
        csv: Path | None = typer.Option(
            None, "--csv",
            help="Path to Schwab positions CSV. Required when "
                 "--source=csv; used as fallback when --source=auto.",
            exists=True, file_okay=True, dir_okay=False,
            readable=True, resolve_path=True,
        ),
        cash: float = typer.Option(
            0.0, "--cash",
            help="Manual cash position (USD). Ignored on Schwab path if "
                 "fetch_positions returns cash from account balances."
        ),
        live: bool = typer.Option(
            False, "--live",
            help="Enable live mode. Default is DRY RUN."
        ),
    ):

Update the body:

1. Validate the source/csv combination early:
       if source == "csv" and csv is None:
           console.print("[red]--source csv requires --csv PATH[/]")
           raise typer.Exit(code=1)
       if source not in {"schwab", "csv", "auto"}:
           console.print(f"[red]Invalid --source: {source}[/]")
           raise typer.Exit(code=1)

2. Banner as before (LIVE MODE vs DRY RUN).

3. Call build_bundle with the source dispatch:
       from core.bundle import build_bundle, write_bundle

       with console.status(f"[cyan]Freezing market state from {source}..."):
           bundle = build_bundle(
               source=source,
               csv_path=csv,
               cash_manual=cash,
           )
           path = write_bundle(bundle)

4. Extend the summary table to show the new fields:
       table.add_row("Data Source", f"[bold green]{bundle.data_source}[/]")
       table.add_row("Source Fingerprint", bundle.data_source_fingerprint)
       table.add_row("Tax Treatment Available",
                     "yes" if bundle.tax_treatment_available else "[yellow]no[/]")

5. Preserve the existing rows for Timestamp, Bundle Hash, Positions,
   Total Value, Cash, Bundle Path, and the enrichment_errors listing.

6. If bundle.data_source == "csv" and source == "auto", print a loud
   yellow warning panel explaining that Schwab was unavailable and
   the run fell back to CSV. This is visible so Bill knows the
   difference between "Schwab worked" and "Schwab quietly failed."

Do NOT:
- Make --csv required unconditionally — it's optional when source is
  auto or schwab
- Import schwab-py or schwab_client at manager.py top level — the
  lazy import in core/bundle.py handles it
- Change any other subcommand
- Break existing CSV-only usage: `manager.py snapshot --source csv
  --csv path.csv --cash 10000` must continue to work
```

---

## Prompt 4 of 6: Smoke tests for the dispatcher and fallback

```text
Read tests/test_bundle_smoke.py (Phase 1b) before writing.

Add these tests to tests/test_bundle_smoke.py:

    def test_invalid_source_raises():
        import pytest
        from core.bundle import build_bundle
        with pytest.raises(ValueError, match="Invalid source"):
            build_bundle(source="garbage", csv_path=None, cash_manual=0.0)


    def test_csv_source_requires_path():
        import pytest
        from core.bundle import build_bundle, SOURCE_CSV
        with pytest.raises(ValueError, match="requires csv_path"):
            build_bundle(source=SOURCE_CSV, csv_path=None, cash_manual=0.0)


    def test_auto_falls_back_to_csv_when_schwab_fails(
        tmp_path, monkeypatch
    ):
        '''
        Simulate Schwab auth failure and verify auto mode falls back
        to CSV with an enrichment_error recording the fallback.
        '''
        from pathlib import Path
        from core.bundle import build_bundle, write_bundle, SOURCE_AUTO
        monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

        sample_csv = Path("-Positions-2025-12-31-082029.csv")
        if not sample_csv.exists():
            import pytest
            pytest.skip("sample CSV not present")

        # Monkeypatch _build_from_schwab to raise RuntimeError, simulating
        # a missing token or expired refresh scenario
        def fake_schwab(cash_manual):
            raise RuntimeError("Simulated Schwab auth failure")
        monkeypatch.setattr(
            "core.bundle._build_from_schwab", fake_schwab
        )

        bundle = build_bundle(
            source=SOURCE_AUTO,
            csv_path=sample_csv,
            cash_manual=10000.0,
        )
        assert bundle.data_source == "csv"
        assert any("fell back to CSV" in err for err in bundle.enrichment_errors)
        assert bundle.position_count > 0


    def test_auto_raises_when_schwab_fails_and_no_csv(
        tmp_path, monkeypatch
    ):
        '''
        Auto mode with no csv fallback path must raise rather than
        producing an empty bundle.
        '''
        import pytest
        from core.bundle import build_bundle, SOURCE_AUTO

        def fake_schwab(cash_manual):
            raise RuntimeError("Simulated Schwab failure")
        monkeypatch.setattr("core.bundle._build_from_schwab", fake_schwab)

        with pytest.raises(RuntimeError, match="no csv_path provided"):
            build_bundle(
                source=SOURCE_AUTO,
                csv_path=None,
                cash_manual=10000.0,
            )


    def test_schwab_path_sets_data_source(monkeypatch, tmp_path):
        '''
        When the Schwab path is taken, the bundle's data_source field
        must be 'schwab' and the source_fingerprint must be non-empty.
        '''
        import pandas as pd
        from core.bundle import build_bundle, SOURCE_SCHWAB
        monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

        # Fake _build_from_schwab to return a minimal valid DataFrame
        def fake_schwab(cash_manual):
            df = pd.DataFrame([
                {
                    "ticker": "UNH",
                    "description": "UnitedHealth",
                    "quantity": 10.0,
                    "price": 500.0,
                    "market_value": 5000.0,
                    "cost_basis": 4500.0,
                    "asset_class": "Equities",
                    "asset_strategy": "US Large Cap",
                    "is_cash": False,
                    "price_source": "schwab_quote",
                    "tax_treatment": "taxable",
                }
            ])
            return df, "abc1234567890def", []

        monkeypatch.setattr("core.bundle._build_from_schwab", fake_schwab)

        bundle = build_bundle(
            source=SOURCE_SCHWAB,
            csv_path=None,
            cash_manual=10000.0,
        )
        assert bundle.data_source == "schwab"
        assert bundle.data_source_fingerprint == "abc1234567890def"
        assert bundle.tax_treatment_available is True

Run:
    python -m pytest tests/test_bundle_smoke.py -v

All existing Phase 1b tests plus these five new tests must pass.
```

---

## Prompt 5 of 6: Live integration smoke test against the real Schwab client

```text
This prompt is a RUNBOOK, not a code change. Execute the steps in
order and report results to Bill.

1. Verify the Schwab token is fresh:
       gsutil ls -l gs://portfolio-manager-tokens/
   Expect to see token_accounts.json and token_market.json modified
   within the last hour (Cloud Function refreshes every 25 min).
   If modified > 2 hours ago, something is wrong with the scheduler —
   stop and investigate.

2. Verify the Schwab client returns a live result:
       python -c "
       from utils.schwab_client import get_accounts_client, fetch_positions
       client = get_accounts_client()
       assert client is not None, 'Accounts client is None — token issue'
       df = fetch_positions(client)
       print(f'{len(df)} positions, total value {df[\"market_value\"].sum():,.2f}')
       assert len(df) > 0
       print('Schwab client is live')
       "
   Expect a non-zero position count and a plausible total value
   (~$545K based on the 2026-04-10 patch notes).

3. Dry-run snapshot using the Schwab path explicitly:
       python manager.py snapshot --source schwab

   The output should show:
       Data Source: schwab
       Source Fingerprint: (16-char hex)
       Tax Treatment Available: yes
       Positions: ~43+
       Total Value: ~$545,000

4. Dry-run snapshot using auto mode (should pick Schwab):
       python manager.py snapshot --source auto --csv -Positions-2025-12-31-082029.csv

   The Schwab path should win. The --csv argument is present only as
   a fallback hint. Data Source should still read 'schwab'.

5. Dry-run snapshot using CSV explicitly (baseline regression):
       python manager.py snapshot --source csv --csv -Positions-2025-12-31-082029.csv --cash 10000

   This must still work identically to Phase 1b. Data Source reads
   'csv'. Tax Treatment Available reads 'no'.

6. Compare the bundle hashes from steps 3 and 5. They MUST differ
   (different timestamps, different positions, different tax
   treatment field availability). The source_fingerprint fields
   should also differ (Schwab fingerprint != CSV SHA).

7. Load both bundles via load_bundle() and verify round-trip:
       python -c "
       import json
       from pathlib import Path
       from core.bundle import load_bundle
       bundles = sorted(Path('bundles').glob('context_bundle_*.json'))
       for b in bundles[-2:]:
           data = load_bundle(b)
           print(f'{b.name}: source={data[\"data_source\"]}, '
                 f'positions={data[\"position_count\"]}, '
                 f'hash={data[\"bundle_hash\"][:16]}')
       "

8. Run a Re-Buy Analyst dry-run against the Schwab-sourced bundle
   to confirm the agent pipeline still works with the new source:
       python manager.py compose --market latest --vault latest
       python manager.py rebuy --ticker UNH --composite latest
   Output should reference the composite hash from the Schwab-sourced
   market bundle. Schwab path should be invisible to the agent — it
   just consumes positions.

If any step fails, STOP and investigate before marking Phase 4 green.
Do not paper over a broken Schwab path by "just using CSV" — the
whole point of Phase 4 is that Schwab is now the default.
```

---

## Prompt 6 of 6: CHANGELOG, CLAUDE.md, and the commit

```text
1. Add a new entry to the TOP of CHANGELOG.md:

   ## [Unreleased] — CLI Migration Phase 4: Schwab API as Bundle Data Source

   ### Added
   - `core/bundle.py` — pluggable data sources via `source` parameter
     (`schwab` | `csv` | `auto`)
   - `_build_from_schwab()` helper that calls the existing
     `utils/schwab_client.fetch_positions()` and wraps it in the
     same bundle contract as the CSV path
   - `_build_from_csv()` helper — refactor of the Phase 1b CSV logic
     into a named helper with a stable return signature
   - `manager.py snapshot --source` flag with 'auto' as the new default;
     `--csv` is now optional
   - Five new smoke tests covering invalid source, required csv_path,
     auto fallback, auto failure without fallback, and Schwab path
     data_source propagation
   - ContextBundle fields: `data_source`, `data_source_fingerprint`,
     `tax_treatment_available`
   - Per-position `tax_treatment` field (populated on Schwab path,
     "unknown" on CSV path)
   - `price_source` vocabulary extended to include "schwab_quote"

   ### Architecture Decision
   The Schwab API integration was already complete (Phase 5-S, April
   2026). Phase 4's actual work was WIRING that existing client into
   the CLI bundle pipeline, not rebuilding it. `core/bundle.py` now
   dispatches on a `source` parameter and calls either
   `_build_from_schwab()` or `_build_from_csv()`, producing the same
   ContextBundle shape either way. Agents downstream see no
   difference — they consume the bundle, not the source.

   `auto` mode is the new default: it tries Schwab first and falls
   back to CSV if Schwab fails, emitting a loud enrichment_error
   recording the fallback. `auto` mode raises if Schwab fails AND
   no csv_path was provided.

   The zero-price yfinance fallback from the 2026-04-10 bug patch
   is now inside `_build_from_schwab()` rather than `app.py`, so
   the CLI benefits from the same fix.

   The existing Schwab client module, token store, Cloud Function,
   and OAuth setup are UNCHANGED. Phase 4 is pure integration work.

   ### Unchanged
   - `utils/schwab_client.py`, `utils/schwab_token_store.py`
   - `cloud_functions/token_refresh/`
   - `scripts/schwab_initial_auth.py`, `scripts/schwab_manual_reauth.py`
   - All Phase 1-3c bundle, vault, composite, and agent logic
   - The Streamlit app (still runs in parallel; Phase 7 retires it)

   **Status:** `manager.py snapshot` defaults to --source auto. Schwab
   is the primary data path; CSV is retained for disaster recovery
   and explicit fallback. All Phase 3+ agents work unchanged against
   Schwab-sourced bundles.

2. Update CLAUDE.md — CLI Migration Status section:

   - Phase 3: COMPLETE
   - Phase 3b: [status at your landing]
   - Phase 3c: [status at your landing]
   - Phase 4: COMPLETE — Schwab API wired into core/bundle.py as the
     default data source; CSV retained as fallback
   - Phase 5: NEXT — remaining three agents + thesis backfill
     completion + Trade_Log rotation extension

3. Commit:

   git add core/bundle.py manager.py tests/test_bundle_smoke.py \
           CHANGELOG.md CLAUDE.md
   git commit -m "Phase 4: Schwab API as pluggable bundle data source

   - core/bundle.py: build_bundle dispatches on source parameter
     (schwab | csv | auto), producing the same ContextBundle shape
   - _build_from_schwab wraps the existing utils/schwab_client
     fetch_positions; no changes to that module
   - auto mode is the new default: try Schwab, fall back to CSV
     on failure with a loud enrichment_error
   - Zero-price yfinance fallback hoisted from app.py into
     _build_from_schwab
   - tax_treatment field per position (populated on Schwab path)
   - manager.py snapshot --source flag, --csv now optional
   - Five new smoke tests covering the dispatch logic
   - Five live runbook steps verified against the ~\$545K portfolio
   - Zero changes to utils/schwab_client.py, the Cloud Function,
     or the OAuth setup

   Unblocks Phase 5 (agent kit completion). Agents consume bundles
   regardless of source — Schwab path is invisible to rebuy_analyst,
   framework_selector, and every future agent."
```

---

## Post-Build Verification Summary

All of these must be true before declaring Phase 4 green:

1. All Phase 1b smoke tests still pass (no regressions on CSV path)
2. The five new Phase 4 smoke tests pass
3. `manager.py snapshot --source schwab` produces a bundle with
   ~43+ positions, total value near \$545K, and data_source="schwab"
4. `manager.py snapshot --source csv --csv <path>` still works
   identically to Phase 1b
5. `manager.py snapshot --source auto` without --csv picks Schwab
   and produces a valid bundle
6. Round-trip verification (load_bundle) passes on both Schwab- and
   CSV-sourced bundles
7. `manager.py rebuy --ticker UNH --composite latest` produces valid
   output when the underlying market bundle was Schwab-sourced
8. `grep -rn "schwab-py\|from schwab" core/` returns ONLY the lazy
   import inside `_build_from_schwab` (not a top-level import)
9. `grep -rn "place_order\|cancel_order" utils/schwab_client.py` returns
   only the safety preamble docstring matches (the existing guarantee
   is preserved)
10. The Cloud Function is still running on its normal 25-min cadence
    (Phase 4 did not touch it)

---

## Gemini CLI Peer Review

```bash
gemini -p "Review the Phase 4 bundle source dispatcher in
core/bundle.py and the snapshot subcommand in manager.py.

Check specifically:

1) Is schwab-py imported lazily inside _build_from_schwab, not at
   the top of core/bundle.py? (Lazy import is required so tests and
   CI can run without schwab-py installed.)

2) Does build_bundle('auto') fall back to CSV ONLY when a csv_path
   was provided? Calling auto with no csv_path and a failing Schwab
   must raise, not produce an empty bundle.

3) Is the zero-price yfinance fallback from the 2026-04-10 patch
   hoisted into _build_from_schwab, not duplicated from app.py?

4) Are _hashable_payload, _normalize_positions, and
   _sha256_canonical from Phase 1b untouched? Phase 4 only adds
   new fields; it does not rewrite the hashing contract.

5) Does every Schwab-sourced position row carry either
   price_source='schwab_quote' or price_source='yfinance_live'
   (the zero-price fallback case)?

6) Does _build_from_schwab handle the case where fetch_positions
   already returns a CASH_MANUAL row (the 2026-04-10 cash
   aggregation patch) WITHOUT duplicating it?

7) Does manager.py snapshot still default to --source auto and
   still accept --source csv --csv path for Phase 1b-compatible
   usage?

8) Are the bundle hash semantics unchanged — same _hashable_payload
   helper, same canonical serialization, same SHA256 over the
   whole payload minus the hash field itself?

9) Is there a grep-safe guarantee that core/bundle.py contains no
   order placement imports? (The existing guarantee in
   utils/schwab_client.py is preserved; Phase 4 must not introduce
   a new path that violates it.)

10) Does the CSV path in _build_from_csv still produce bundles
    whose source_csv_path and source_csv_sha256 fields match what
    Phase 1b produced, so old bundles stay loadable?"
```

---

## What Phase 4 explicitly does NOT do (recap)

- No changes to `utils/schwab_client.py`, `utils/schwab_token_store.py`,
  or the Cloud Function. These are live in production.
- No new Schwab endpoints. No options chain (Phase 8a). No order
  placement, ever.
- No deletion of the CSV path. It's retained as `--source csv` and as
  the auto-mode fallback.
- No changes to agents. They consume bundles regardless of source.
- No retirement of `app.py` — that's Phase 7.
- No new data sources beyond Schwab and CSV. FMP, yfinance, and
  Finnhub remain enrichment helpers, not primary sources.

---

## Why this phase is smaller than you might expect

Phase 4 is mostly a **wiring** phase because the Schwab integration
work already happened. If you read the original master plan, Phase 4
was scoped as "Schwab API integration" with an effort estimate of 2-3
days. That estimate assumed starting from zero. You aren't starting
from zero — you're starting from a working, token-refreshed,
bug-patched, $545K-tested production Schwab client. The actual work
is exposing that client to the CLI path via a single dispatcher
function, and it's a half-day of focused work plus verification.

Don't inflate the scope. Don't rebuild what already works. The Phase
4 win is "my CLI agents now consume live portfolio data with no
manual CSV download," and the path to that win is short.

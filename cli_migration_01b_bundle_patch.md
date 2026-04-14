# CLI Migration Phase 1b — core/bundle.py Correctness Patch
# Target: Claude Code or Gemini CLI 3 Pro
# Prerequisite: core/bundle.py from cli_migration_01 already exists and imports cleanly.

## Overview

The initial `core/bundle.py` implementation is structurally correct but has four
correctness bugs that will cause non-deterministic hashes, schema drift, and
silent audit gaps. This prompt patches all four in a single pass, preserves the
public API (`build_bundle`, `write_bundle`, `load_bundle`), and adds a
provenance field (`price_source`) to every position.

Do not rewrite the file from scratch. Apply the changes as targeted edits so
the diff is reviewable.

## The four bugs being fixed

1. **Hash shape drift risk.** `build_bundle` hashes a payload dict assembled
   by hand; `load_bundle` hashes `data.copy()` with `bundle_hash` popped.
   These happen to produce the same bytes today but there is no single source
   of truth, so a future field addition could silently break round-trips.
   Fix: one `_hashable_payload()` helper used by both sides.

2. **Non-deterministic position serialization.** `df.to_dict(orient="records")`
   returns numpy scalars (`numpy.float64`, `numpy.int64`), pandas `Timestamp`
   objects, and `NaN` values. `json.dumps(..., default=str)` silently coerces
   these, but the output is not guaranteed stable across numpy/pandas versions,
   and `NaN` round-trips as the string `"nan"` which is lossy. This is the
   same class of bug as the existing `sanitize_for_sheets()` pattern in the
   project.
   Fix: `_normalize_positions()` coerces to JSON-native types with
   `NaN → None`.

3. **Inconsistent CASH_MANUAL injection.** The synthetic cash row is only
   added when `cash_manual > 0`. Bundles with zero cash have a different
   schema than bundles with nonzero cash. Downstream filters on
   `ticker == 'CASH_MANUAL'` will sometimes find nothing.
   Fix: always inject the row, even at zero.

4. **Silent stale-price fallback.** When yfinance enrichment fails, the code
   keeps the CSV price with no marker on the position itself. The error is
   logged to `enrichment_errors` but there is no way to tell from a position
   row whether its price is live or stale.
   Fix: add a `price_source` field per position
   (`"yfinance_live"` | `"csv_fallback"` | `"manual"`).

---

## Prompt 1 of 1: Apply the patch to core/bundle.py

```text
Read core/bundle.py fully before making changes. Apply the following edits
as targeted modifications — do not rewrite the file.

=== EDIT 1: Add two helper functions ===

Insert these two new functions immediately after _capture_environment() and
before build_bundle():

    def _hashable_payload(data: dict) -> dict:
        """
        Canonical pre-hash view of a bundle payload.

        Single source of truth for what gets hashed. Both build_bundle() and
        load_bundle() route through this so a future field addition cannot
        cause the hash shape to drift between write and read paths.
        """
        return {k: v for k, v in data.items() if k != "bundle_hash"}


    def _normalize_positions(records: list[dict]) -> list[dict]:
        """
        Coerce numpy/pandas scalars to JSON-native types.

        df.to_dict(orient='records') returns dicts whose values are numpy
        scalars, pandas Timestamps, and NaN floats. These do not serialize
        deterministically across library versions and NaN is lossy under
        json.dumps. This normalizer produces values that json.dumps can
        round-trip without information loss.

        Rules:
          - NaN / NaT  -> None
          - bool       -> bool (must be checked before int; numpy bool is int)
          - int/float/str/None -> passthrough
          - numpy scalar -> .item() to native Python
          - anything else (Timestamp, etc.) -> str()
        """
        out = []
        for r in records:
            clean = {}
            for k, v in r.items():
                if v is None:
                    clean[k] = None
                elif isinstance(v, bool):
                    clean[k] = v
                elif isinstance(v, (int, float, str)):
                    # pd.isna on a plain float handles NaN; guard on type first
                    if isinstance(v, float) and pd.isna(v):
                        clean[k] = None
                    else:
                        clean[k] = v
                elif pd.isna(v):
                    clean[k] = None
                elif hasattr(v, "item"):
                    # numpy scalar — unwrap to Python native
                    try:
                        clean[k] = v.item()
                    except (ValueError, AttributeError):
                        clean[k] = str(v)
                else:
                    clean[k] = str(v)
            out.append(clean)
        return out

=== EDIT 2: Patch build_bundle() — enrichment block ===

Find this block in build_bundle():

    live_prices = {}
    for ticker in unique_tickers:
        try:
            yt = yfinance.Ticker(ticker)
            # Try fast_info first
            try:
                price = yt.fast_info['lastPrice']
            except (AttributeError, KeyError, Exception):
                # Fallback to history
                hist = yt.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                else:
                    raise ValueError(f"No price data found for {ticker}")
            
            live_prices[ticker] = price
        except Exception as e:
            enrichment_errors.append(f"Failed to enrich {ticker}: {str(e)}")
            # Keep the price from CSV if enrichment fails
            pass

    # Update prices where we have live data
    def get_price(row):
        return live_prices.get(row['ticker'], row['price'])
    
    df['price'] = df.apply(get_price, axis=1)

Replace it with:

    # Default every row to csv_fallback; flip to yfinance_live only on success.
    df['price_source'] = 'csv_fallback'

    live_prices: dict[str, float] = {}
    for ticker in unique_tickers:
        try:
            yt = yfinance.Ticker(ticker)
            try:
                price = yt.fast_info['lastPrice']
            except (AttributeError, KeyError, Exception):
                hist = yt.history(period="1d")
                if hist.empty:
                    raise ValueError(f"No price data found for {ticker}")
                price = hist['Close'].iloc[-1]
            live_prices[ticker] = float(price)
        except Exception as e:
            enrichment_errors.append(f"Failed to enrich {ticker}: {str(e)}")

    if live_prices:
        mask = df['ticker'].isin(live_prices.keys())
        df.loc[mask, 'price'] = df.loc[mask, 'ticker'].map(live_prices)
        df.loc[mask, 'price_source'] = 'yfinance_live'

=== EDIT 3: Patch build_bundle() — CASH_MANUAL injection ===

Find this block:

    # d. Inject synthetic CASH_MANUAL
    if cash_manual > 0:
        cash_row = {
            'ticker': 'CASH_MANUAL',
            'description': 'Manual Cash Entry',
            'quantity': float(cash_manual),
            'price': 1.0,
            'market_value': float(cash_manual),
            'cost_basis': float(cash_manual),
            'asset_class': 'Cash',
            'asset_strategy': 'Cash',
            'is_cash': True
        }
        df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

Replace it with (no conditional, always inject, and include price_source):

    # d. Always inject synthetic CASH_MANUAL row so bundle schema is
    # consistent across zero-cash and nonzero-cash snapshots.
    cash_row = {
        'ticker': 'CASH_MANUAL',
        'description': 'Manual Cash Entry',
        'quantity': float(cash_manual),
        'price': 1.0,
        'market_value': float(cash_manual),
        'cost_basis': float(cash_manual),
        'asset_class': 'Cash',
        'asset_strategy': 'Cash',
        'is_cash': True,
        'price_source': 'manual',
    }
    df = pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

=== EDIT 4: Patch build_bundle() — normalize before hashing ===

Find this line:

    positions = df.to_dict(orient="records")

Replace it with:

    positions = _normalize_positions(df.to_dict(orient="records"))

=== EDIT 5: Patch build_bundle() — route hashing through the helper ===

Find this line:

    # g. Compute hash (without bundle_hash field)
    bundle_hash = _sha256_canonical(payload)

Replace it with:

    # g. Compute hash via the single source of truth helper
    bundle_hash = _sha256_canonical(_hashable_payload(payload))

=== EDIT 6: Patch load_bundle() — route hashing through the helper ===

Find the current load_bundle() body:

    def load_bundle(path: Path) -> dict:
        """Read, parse, and verify the hash matches."""
        with open(path, "r") as f:
            data = json.load(f)
        
        # Recompute the canonical hash with bundle_hash removed
        payload = data.copy()
        actual_hash = payload.pop("bundle_hash")
        
        expected_hash = _sha256_canonical(payload)
        
        if actual_hash != expected_hash:
            raise ValueError(
                f"Bundle hash mismatch! Filename: {path.name}\n"
                f"Stored: {actual_hash}\n"
                f"Computed: {expected_hash}"
            )
            
        return data

Replace it with:

    def load_bundle(path: Path) -> dict:
        """
        Read, parse, and verify the hash matches.

        Both the write path and this read path compute the hash via
        _hashable_payload() so the pre-hash view cannot drift.
        """
        with open(path, "r") as f:
            data = json.load(f)

        stored_hash = data.get("bundle_hash")
        if not stored_hash:
            raise ValueError(f"Bundle missing bundle_hash field: {path.name}")

        expected_hash = _sha256_canonical(_hashable_payload(data))

        if stored_hash != expected_hash:
            raise ValueError(
                f"Bundle hash mismatch! Filename: {path.name}\n"
                f"Stored:   {stored_hash}\n"
                f"Computed: {expected_hash}"
            )

        return data

=== Do NOT change ===

- The ContextBundle dataclass fields
- The BUNDLE_DIR or BUNDLE_SCHEMA_VERSION constants
- The __all__ export list
- write_bundle() — it already uses asdict() which picks up the new
  price_source field automatically because it lives inside the positions
  list, not on the dataclass itself
- Any imports (pd is already imported for pd.isna)
```

---

## Post-Patch Verification

Run these commands in order. Each must pass before the next.

```bash
# 1. Imports still clean
python -c "from core.bundle import build_bundle, write_bundle, load_bundle; print('OK')"

# 2. Build a real bundle against the sample CSV
python -c "
from pathlib import Path
from core.bundle import build_bundle, write_bundle, load_bundle

b = build_bundle(Path('-Positions-2025-12-31-082029.csv'), cash_manual=10000.0)
p = write_bundle(b)
print(f'Wrote: {p}')
print(f'Hash:  {b.bundle_hash}')
print(f'Positions: {b.position_count}')
print(f'Total:     \${b.total_value:,.2f}')
print(f'Errors:    {len(b.enrichment_errors)}')
"

# 3. Round-trip must succeed (this is the correctness proof)
python -c "
from pathlib import Path
from core.bundle import load_bundle
latest = sorted(Path('bundles').glob('*.json'))[-1]
data = load_bundle(latest)
print(f'Round-trip OK: {latest.name}')
print(f'Hash verified: {data[\"bundle_hash\"][:16]}...')
"

# 4. price_source is present on every position
python -c "
import json
from pathlib import Path
latest = sorted(Path('bundles').glob('*.json'))[-1]
data = json.loads(latest.read_text())
sources = {}
for p in data['positions']:
    src = p.get('price_source', 'MISSING')
    sources[src] = sources.get(src, 0) + 1
print('price_source distribution:', sources)
assert 'MISSING' not in sources, 'Every position must have price_source'
assert any(p['ticker'] == 'CASH_MANUAL' for p in data['positions']), 'CASH_MANUAL must be present'
print('OK')
"

# 5. Zero-cash bundle must still contain CASH_MANUAL row
python -c "
from pathlib import Path
from core.bundle import build_bundle
b = build_bundle(Path('-Positions-2025-12-31-082029.csv'), cash_manual=0.0)
cash_rows = [p for p in b.positions if p['ticker'] == 'CASH_MANUAL']
assert len(cash_rows) == 1, f'Expected 1 CASH_MANUAL row, got {len(cash_rows)}'
assert cash_rows[0]['quantity'] == 0.0
assert cash_rows[0]['price_source'] == 'manual'
print('Zero-cash schema consistent: OK')
"

# 6. Tamper detection — mutate total_value and confirm load_bundle raises
python -c "
import json
from pathlib import Path
from core.bundle import load_bundle
latest = sorted(Path('bundles').glob('*.json'))[-1]
data = json.loads(latest.read_text())
data['total_value'] = 999999999.99
tampered = latest.with_suffix('.tampered.json')
tampered.write_text(json.dumps(data, indent=2))
try:
    load_bundle(tampered)
    print('FAIL: tamper went undetected')
except ValueError as e:
    print(f'Tamper detected: {str(e).splitlines()[0]}')
finally:
    tampered.unlink()
"

# 7. Determinism probe — back-to-back builds should differ ONLY in fields
#    that legitimately change (timestamp, and possibly live prices if the
#    market moved between calls). The hash MUST differ because the timestamp
#    is part of the hashable payload. This confirms the hash is sensitive to
#    the inputs it should be sensitive to.
python -c "
from pathlib import Path
from core.bundle import build_bundle
a = build_bundle(Path('-Positions-2025-12-31-082029.csv'), cash_manual=10000.0)
b = build_bundle(Path('-Positions-2025-12-31-082029.csv'), cash_manual=10000.0)
print(f'A: {a.bundle_hash[:16]}...')
print(f'B: {b.bundle_hash[:16]}...')
print(f'Differ (expected): {a.bundle_hash != b.bundle_hash}')
"
```

All seven checks must pass. If check 3 (round-trip) fails, the normalization
is still not deterministic and we need to dig into which field is drifting —
the most likely culprit is a pandas Timestamp or a numpy type that slipped
through `_normalize_positions`. Add a print statement comparing the
canonical serializations of the two payloads to find the delta.

---

## Gemini CLI Peer Review

```bash
gemini -p "Review the patched core/bundle.py. Check specifically:
1) Is there ONE function responsible for the pre-hash view, and do BOTH
   build_bundle and load_bundle route through it?
2) Does _normalize_positions handle numpy.bool_ correctly (numpy bool is
   a subclass of int, so the isinstance order matters)?
3) Is CASH_MANUAL injected unconditionally, including when cash_manual=0.0?
4) Does every position (including CASH_MANUAL and csv_fallback rows) carry
   a price_source field?
5) Does load_bundle raise ValueError with a clear message on hash mismatch
   AND on missing bundle_hash field?
6) Are there any places where pd.Timestamp or numpy scalars could still
   reach json.dumps without going through _normalize_positions first?"
```

---

## Commit After Green

Once all seven checks pass, this is the first real milestone of the CLI
migration and deserves a clean git commit:

```bash
git add core/bundle.py
git commit -m "core/bundle: deterministic hashing + price provenance

- Single _hashable_payload() helper used by build and load paths
- _normalize_positions() coerces numpy/pandas scalars to JSON-native
- CASH_MANUAL row always injected for schema consistency
- price_source field per position (yfinance_live|csv_fallback|manual)
- load_bundle raises on missing or mismatched hash

Closes the four correctness gaps in the Phase 1 scaffold. Bundle
round-trip and tamper detection verified against real CSV."
```

Then you are cleared to move to Prompt 3 of cli_migration_01
(manager.py Typer CLI).

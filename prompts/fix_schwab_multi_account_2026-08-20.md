# Build Prompt: Schwab Allowlist Fail-Closed

**Author:** Claude (Chief Architect) / Cursor (audit re-author), 2026-08-20
**Executor:** Cursor Agent
**Prompt version:** 1.1.0
**Supersedes:** `prompts/fix_schwab_multi_account_2026-08-20.md` v1.0.0 (misdiagnosed under-aggregation)
**Type:** Correctness hardening. Not a feature.

**Audit finding (2026-08-20):** Multi-account allowlist already shipped 2026-08-03 as `config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` (three of six linked accounts). `fetch_positions()` / `fetch_transactions()` / `fetch_tax_lots()` already gate on `_is_primary_account()`. The real gap is **fail-open when the suffix list is empty** (warn once, then aggregate everything). Also: `fetch_positions()` docstring still says "ALL linked Schwab accounts" and contradicts the filter at the call site.

**Chase / RE funding accounts are out of scope** for this repo (Bill, 2026-08-20). Do not add `TAX_CONTROL_EXTRA` or any `8895` widening. Schwab reserve `...8895` stays in the RE Property Manager.

---

## Sequencing

Safe anytime relative to store Phase 1. Prefer before dual-write so position totals are stable during the streak. **No** `core/store/` or bundle schema changes.

---

## Scope boundary

**In scope:** `utils/schwab_client.py`, `config.py` only if documenting the fail-closed contract.

**Out of scope:** second allowlist (`SCHWAB_ACCOUNT_ALLOWLIST`), Chase, Tax_Control extras, store migration, agents, Sheets layout.

---

## Step 0 — Verification gate (paste RAW stdout under each)

- [ ] **Confirm existing allowlist gate**

```text
rg -n "def fetch_positions|def _is_primary_account|SCHWAB_PRIMARY_ACCOUNT_SUFFIXES|_warn_if_unscoped" utils/schwab_client.py config.py
```

- [ ] **Confirm empty-list behavior today (fail-open)**

```text
rg -n "if not suffixes|return True|aggregating ALL" utils/schwab_client.py
```

- [ ] **No order endpoints**

```text
rg -n "order|place_order|Order" utils/schwab_client.py
```

If `_is_primary_account` is missing, STOP — this prompt assumes the 2026-08-03 fix is present.

---

## Required behaviour after fix

1. Keep `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` as the single allowlist (default `6499,8767,5119`).
2. When the list is **empty**, **fail closed**: raise a clear error (or return a hard health failure) unless an explicit `--force-unscoped` / `SCHWAB_FORCE_UNSCOPED=1` escape hatch is set.
3. Fix `fetch_positions()` (and sibling) docstrings to describe allowlist aggregation, not "ALL accounts."
4. Non-allowlisted API accounts: log INFO and exclude (unchanged).
5. Do not invent a second allowlist name.

---

## Post-build verification checklist (raw stdout required)

- [ ] `python -c "import config; print(config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES)"` — three primary suffixes; no Chase/8895 requirement
- [ ] Empty suffixes without force — raises / fails closed (show traceback or message)
- [ ] `rg -n "ALL linked Schwab accounts" utils/schwab_client.py` — no matches in live docstrings (or only historical comments)
- [ ] `git diff --stat` — no changes under `core/store/`, `core/bundle.py`, `utils/agents/`

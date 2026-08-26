# Sheets hand-edit inventory (Phase 2 pre-flip)

**Date:** 2026-08-21  
**Purpose:** Before `STORE_PRIMARY=sqlite`, list every tab Bill may edit by hand and whether a CLI path exists after cutover. After the flip, a manual Sheet edit on a **store-backed** surface is cosmetic until the next dual-write / sync — nothing that reads via `get_store()` will see it.

**Flip scope:** Phase 2 only routes **ledger / Tier-2** reads (`transactions`, `realized_gl`, `trade_log`, `holdings_current`, tax_control where applicable) through `get_store()`. Market bundle positions remain Schwab-sourced. Tabs not on the store read path stay Sheets SoR (`Flip-safe = N/A`).

| Tab | Hand-edited? | CLI / code path after cutover | Flip-safe? |
|---|---|---|---|
| `0_DASHBOARD` | no | `pm refresh dashboard` / morning STEP 5 — clear-and-rebuild | N/A (computed) |
| `Holdings_Current` | no (pipeline) | `pm sync` / morning sync; store shadow | yes |
| `Holdings_History` | rare / none observed | none dedicated | N/A (not store-primary read) |
| `Daily_Snapshots` | no | pipeline snapshot writers | N/A |
| `Transactions` | no (Schwab sync) | `pm sync transactions --live`; store shadow | yes |
| `Target_Allocation` | **yes — manual-only** | none (agents must not write) | **N/A — Sheets remains SoR; not on STORE_PRIMARY read set** |
| `Risk_Metrics` | rare | none dedicated | N/A |
| `Income_Tracking` | rare | none dedicated | N/A |
| `Realized_GL` | via import, not cell-edit | `pm sync realized-gl` / `--merge` / `--replace` | yes |
| `Config` | rare | none | N/A |
| `Logs` | no | pipeline | N/A |
| `Agent_Outputs` | no (agent sandbox) | agent writers only; not authoritative | N/A |
| `Agent_Outputs_Archive` | no | archive path | N/A |
| `Disagreements` | rare | none dedicated | N/A |
| `AI_Suggested_Allocation` | no (agent sandbox) | podcast / weekly sync writers | N/A |
| `Decision_Log` | **yes** | none automated | **N/A — Sheets remains SoR; not on STORE_PRIMARY read set** |
| `Trade_Log` | rare (prefer staging promote) | `pm journal promote`; derive/attribution refresh | yes |
| `Trade_Log_Staging` | **yes — Status column** | `pm journal promote` (acts on approve/approved) | **N/A — Sheets UI for Status; promote writes Trade_Log which is shadowed** |
| `Rotation_Review` | no | `pm trade review` / attribution | yes (shadowed) |
| `Tax_Control` | no | `pm refresh tax --live` | yes |
| `Valuation_Card` | no | `build_valuation_card` / morning | N/A (computed) |
| `Decision_View` | no | Crosshairs / Decision_View builders | N/A (computed) |

### Blocked rows requiring Bill override before flip

**None.** No store-backed read surface is hand-edited without a CLI path. Manual tabs (`Target_Allocation`, `Decision_Log`, staging Status) remain Sheets SoR and are outside the Phase 2 `STORE_PRIMARY` read set.

### Sign-off

- [x] Inventory authored 2026-08-21 (Phase 2 executor). No blocked rows → flip of ledger reads may proceed after streak + parity.
- Bill may still override any **N/A** row later without undoing the flip; those tabs never depended on `STORE_PRIMARY`.

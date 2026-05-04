# Thesis Managed Regions Specification

This document defines the canonical HTML-comment fences used by `pm vault sync` to inject automated data into investment thesis files while preserving hand-written prose.

## Core Invariant
Hand-written prose outside of these fences MUST NOT be touched. If a fence is missing, the sync tool may append it to the end of the file or skip it, depending on the `--force` flag.

## Fence Definitions

### 1. Position State
**Region Name:** `position_state`
**Purpose:** Summary of current holding status (quantity, cost basis, unrealized G/L).
**Fences:**
```markdown
<!-- region:position_state -->
... (automated content) ...
<!-- endregion:position_state -->
```

### 2. Sizing
**Region Name:** `sizing`
**Purpose:** Allocation metrics (current weight, target weight, drift).
**Fences:**
```markdown
<!-- region:sizing -->
... (automated content) ...
<!-- endregion:sizing -->
```

### 3. Transaction Log
**Region Name:** `transaction_log`
**Purpose:** The most recent N transactions for this ticker from the `Transactions` tab.
**Fences:**
```markdown
<!-- region:transaction_log -->
... (automated content) ...
<!-- endregion:transaction_log -->
```

### 4. Realized G/L
**Region Name:** `realized_gl`
**Purpose:** Summary of closed lots and historical performance from `Realized_GL`.
**Fences:**
```markdown
<!-- region:realized_gl -->
... (automated content) ...
<!-- endregion:realized_gl -->
```

### 5. Change Log
**Region Name:** `change_log`
**Purpose:** Audit trail of `pm vault sync` executions.
**Fences:**
```markdown
<!-- region:change_log -->
... (automated content) ...
<!-- endregion:change_log -->
```

## Parsing Rules
1. **Case Sensitivity:** Region names are lower-case.
2. **Whitespace:** Fences should be on their own lines.
3. **Round-trip:** Content within fences is replaced entirely on each run.

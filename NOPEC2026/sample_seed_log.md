# Sample Seed Log — NOPEC SOC 1 2025 Examination

**Engagement:** NOPEC [Electric | Gas]
**Examination Period:** January 1, 2025 – December 31, 2025
**Purpose:** Document every random sample selection seed value used during
testing to ensure reviewer re-performance per AT-C 205 documentation
requirements.

> **Standard Seed:** Use period-end date as YYYYMMDD (i.e., `20251231`) unless
> a specific control requires interim selection, in which case document the
> rationale.

---

## Standard Entry Format

```
================================================================================
Selection Date:       [YYYY-MM-DD]
Workpaper Reference:  [WP-XXX-NN]
Control Reference:    [CC-XX-NN]
Control Description:  [brief]
Control Frequency:    [Annual | Quarterly | Monthly | Weekly | Daily | Multi/day]
Population File:      [path + SHA-256 from evidence register]
Population Size:      [count]
Sample Size:          [count] — Rationale: [AICPA tier reference]
Selection Method:     [Random | Stratified | Targeted | Haphazard]
Random Seed:          [value]
Selection Tool:       [Python pandas / R / specify]
Output File:          [path + SHA-256 of resulting sample file]
Prepared By:          [initials]   Date: [YYYY-MM-DD]
Reviewed By:          [initials]   Date: [YYYY-MM-DD]
================================================================================
```

---

## Selection Entries

### Entry [001]
```
================================================================================
Selection Date:       
Workpaper Reference:  
Control Reference:    
Control Description:  
Control Frequency:    
Population File:      
Population Size:      
Sample Size:          
Selection Method:     
Random Seed:          
Selection Tool:       Python 3.x / pandas — DataFrame.sample(random_state=<seed>)
Output File:          
Prepared By:          
Reviewed By:          
================================================================================
```

---

## Reproducibility Verification

A reviewer should be able to regenerate any sample by:

1. Verifying the population file hash against the evidence register
2. Running the same selection script with the documented seed
3. Comparing the resulting hash to the documented output file hash

```python
import pandas as pd
import hashlib

# Re-perform selection
df = pd.read_csv('<population_file>')
sample = df.sample(n=<sample_size>, random_state=<seed>)

# Verify hash matches documentation
with open('<output_file>', 'rb') as f:
    actual = hashlib.sha256(f.read()).hexdigest()
print(f"Match: {actual == '<expected_hash>'}")
```

---

## Targeted / Judgmental Selection Justification

When non-random selection is used, document the rationale here. Targeted
selection alone is generally not sufficient for Type II opinion support unless
combined with a risk-based justification reviewed by the engagement partner.

| Date | Control | Justification | Partner Approval |
|---|---|---|---|
|  |  |  |  |

---

*All sample selections subject to engagement partner review.*

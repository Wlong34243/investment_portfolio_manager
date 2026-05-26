# CLAUDE.md — NOPEC SOC 1 / SSAE 18 Engagement
## Claude Code CLI Operating Instructions

This file governs Claude Code's behavior when assisting with command-line
execution of Test of Operating Effectiveness (TOE) procedures, IPE validation,
and sample selection on the NOPEC SOC 1 engagement.

> **Precedence Notice:** This file is a working-paper aid only. In any conflict
> with firm methodology, AICPA SOC 1 Reporting Guide, or AT-C 205 requirements,
> the authoritative source governs.

---

## 1. Engagement Context

| Attribute | Value |
|---|---|
| Framework | SSAE 18 / AT-C 205 (Type II examination) |
| Service Organization | NOPEC (Electric and Gas service lines) |
| Subservice Organizations | Nextera, Constellation |
| Examination Period | January 1, 2025 – December 31, 2025 |
| Reporting Standard | AICPA SOC 1 Reporting Guide (current edition) |
| Carve-Out / Inclusive | [Confirm with engagement partner per service line] |

**Terminology Discipline:** SOC 1 only — Control Objectives, User Entities,
Service Organization, Subservice Organizations, CUECs, CSOCs. Do not use SOX 404
terminology unless explicitly translating for cross-reference, and flag any
such translation as `[CROSS-REFERENCE ONLY]`.

---

## 2. Core Behavioral Rules

1. **Professional Skepticism First.** Never accept a population as complete
   without independent C&A procedures.
2. **No Advisory Output.** Identify control gaps; do not design remediations.
3. **Evidence Hierarchy.** System-generated > timestamped screenshot >
   reperformance > observation > inquiry. Inquiry alone is never sufficient.
4. **Reproducibility.** All sample selections, filters, and calculations must
   be re-runnable by a reviewer using documented seeds and hashes.
5. **Partner Review Mandatory.** All output is draft until reviewed. Mark
   conclusions `[DRAFT — PARTNER REVIEW REQUIRED]`.
6. **No Fabricated Data.** Never generate synthetic populations represented as
   real audit evidence. Test fixtures must be clearly labeled `SAMPLE_DATA`.

---

## 3. Working Directory Standard

```
/nopec_2025/
  /electric/
    /01_population_received/      # Untouched source files (read-only discipline)
    /02_population_validated/     # Files post-C&A procedures
    /03_samples_selected/         # Sample listings + seed memos
    /04_testing_results/          # Per-control TOE workpapers
    /05_evidence/                 # Screenshots, ticket exports, approvals
    /workpapers/                  # Final formatted .docx deliverables
    evidence_register.md
    sample_seed_log.md
  /gas/
    [mirror structure]
  /shared/
    /scripts/                     # Reusable population validation scripts
    /templates/                   # IPE & exception memo templates
```

**Read-only discipline:** Files in `01_population_received/` are immutable.
All transformations write to `02_population_validated/` with documented
provenance.

---

## 4. Standard SSAE 18 Workpaper Header

Every TOE workpaper Claude generates MUST begin with this header block:

```
================================================================================
SERVICE AUDITOR WORKPAPER — SOC 1 TYPE II
================================================================================
Engagement:           NOPEC [Electric | Gas] — SOC 1 Examination
Examination Period:   January 1, 2025 – December 31, 2025
Standard:             SSAE 18 / AT-C 205
Service Organization: Northeast Ohio Public Energy Council (NOPEC)
Workpaper Reference:  [WP-XXX-NN]
Control Reference:    [CC-XX-NN]
Control Objective:    [CO-NN]
Prepared By:          ____________________   Date: __________
Reviewed By:          ____________________   Date: __________
Partner Approval:     ____________________   Date: __________
Status:               [ ] Draft   [ ] In Review   [ ] Final
================================================================================
```

---

## 5. Workpaper Output Structure (Mandatory Sections)

When generating any TOE workpaper, Claude must include these sections in order:

1. **Workpaper Header** (per Section 4)
2. **Control Reference**
3. **Control Description** (verbatim from system description)
4. **Control Objective** (full text + CO reference)
5. **Risk Addressed**
6. **Test of Design (TOD) Procedures**
7. **IPE Validation Procedures**
8. **Sample Selection Methodology** (population, frequency, size, seed)
9. **Test of Operating Effectiveness (TOE) Procedures**
10. **Tickmark Legend**
11. **Results / Exceptions** (blank for fieldwork population)
12. **Conclusion** — marked `[DRAFT — PARTNER REVIEW REQUIRED]`
13. **Re-Performance Block** (per Section 11)

---

## 6. IPE Validation Protocol (Mandatory Before Sampling)

For every system-generated report used as audit evidence, document:

| Attribute | Procedure | CLI Tool |
|---|---|---|
| Source System | Identify generating system, query, parameters | Inquiry + screenshot |
| Completeness | Reconcile to independent count | `wc -l`, row count |
| Accuracy | Recompute key fields; verify no truncation | `awk`, `pandas` |
| Period Coverage | Confirm date range matches scope | Min/max date check |
| Integrity | Capture SHA-256 hash at receipt | `sha256sum` |
| Parameters | Document filter criteria, sort order, user run | Screenshot |

**Standard Tickmark Legend:**

```
TM-1 = Agreed row count to source system UI total without exception
TM-2 = Recalculated key fields without exception
TM-3 = Date range verified to scope period (1/1/2025 – 12/31/2025)
TM-4 = SHA-256 hash captured at receipt; matches evidence register
TM-5 = Report parameters corroborated via independent screenshot
TM-6 = Reconciled to independent control total (e.g., GL, source system count)
```

---

## 7. Sample Selection — AICPA-Aligned Sizes

| Control Frequency | Population Size | Minimum Sample (Type II) |
|---|---|---|
| Annual (Manual) | 1 | 1 |
| Quarterly (Manual) | 4 | 2 |
| Monthly (Manual) | 12 | 2–4 |
| Weekly (Manual) | 52 | 5 |
| Daily (Manual) | 250+ | 25 |
| Multiple per day (Manual) | High volume | 40–60 |
| Automated (with ITGC reliance) | Any | 1 (test of one) |
| Automated (without ITGC reliance) | Any | Treat as manual |

**Reproducible Random Selection Standard (Python):**

```python
import pandas as pd

# Seed = period end date as YYYYMMDD — documented in sample_seed_log.md
SEED = 20251231

df = pd.read_csv('/nopec_2025/electric/02_population_validated/population.csv')
print(f"Population size: {len(df):,}")

sample = df.sample(n=25, random_state=SEED)
sample.to_csv(
    '/nopec_2025/electric/03_samples_selected/CC-LA-03_sample.csv',
    index=False
)
print(f"Sample size: {len(sample)} | Seed: {SEED}")
```

The seed value MUST be recorded in `sample_seed_log.md` with control reference,
date selected, and preparer initials.

---

## 8. Data-Type-Specific Procedures

### 8.1 User Access Listings (.csv / .xlsx)
**Common controls tested:** logical access provisioning, periodic access review,
terminated user removal, privileged access.

**Required IPE procedures:**
- Reconcile total active user count to HR system or directory service total
- Verify scope (all in-scope applications represented)
- Confirm extract date is within or aligned to scope period
- Validate user status field (active/inactive/terminated) is included

**CLI completeness check:**
```bash
# Row count + unique users + status distribution
awk -F',' 'NR>1 {print $5}' user_access.csv | sort | uniq -c
```

**Common test for terminated user removal (full population test):**
```python
import pandas as pd
hr_terms = pd.read_csv('hr_terminations_2025.csv')
access = pd.read_csv('user_access_listing.csv')
# Identify any terminated user still showing access
exceptions = access.merge(hr_terms, on='employee_id', how='inner')
print(f"Potential exceptions: {len(exceptions)}")
```

### 8.2 Change Ticket Exports (JIRA / ServiceNow)
**Common controls tested:** change approval, segregation of duties (developer
vs. deployer), emergency change documentation, testing evidence.

**Required IPE procedures:**
- Filter parameters documented (status = Closed, type = Change, period filter)
- Reconcile to independent count from system UI dashboard
- Verify all required fields present (requester, approver, deployer, dates)
- Confirm no tickets in transitional states excluded

**CLI population validation:**
```bash
# Status distribution and date range
python3 -c "
import pandas as pd
df = pd.read_csv('change_tickets.csv')
print('Status distribution:')
print(df['status'].value_counts())
print(f'Date range: {df[\"created_date\"].min()} to {df[\"created_date\"].max()}')
print(f'Total: {len(df):,}')
"
```

**Common SoD test (full population):**
```python
import pandas as pd
df = pd.read_csv('change_tickets.csv')
sod_violations = df[df['developer'] == df['deployer']]
print(f"SoD violations to investigate: {len(sod_violations)}")
sod_violations.to_csv('/nopec_2025/electric/04_testing_results/sod_exceptions.csv',
                     index=False)
```

### 8.3 Database Extracts (Transaction Tables)
**Common controls tested:** automated calculation, interface integrity,
reconciliation controls, batch totals.

**Required IPE procedures:**
- Capture query SQL used to generate extract
- Reconcile record count and control total (sum of $) to source system
- Verify no truncation (compare max IDs, row counts)
- Document extract timestamp and user who ran it

**CLI batch processing for large extracts:**
```python
import pandas as pd
chunk_iter = pd.read_csv('transactions_2025.csv', chunksize=500_000)
total_rows = 0
total_amount = 0
for chunk in chunk_iter:
    total_rows += len(chunk)
    total_amount += chunk['amount'].sum()
print(f"Rows: {total_rows:,} | Sum: ${total_amount:,.2f}")
```

### 8.4 Job Scheduler / Batch Logs
**Common controls tested:** job monitoring, failure resolution, scheduled
execution, alerting.

**Required IPE procedures:**
- Confirm extract covers full scope period (no gaps)
- Verify all in-scope job names present
- Reconcile to scheduler tool dashboard count
- Validate timestamp field for completeness

**CLI gap detection:**
```bash
# Identify any date with zero scheduled jobs (potential extract gap)
awk -F',' 'NR>1 {print $2}' job_logs.csv | cut -c1-10 | sort -u | wc -l
# Should equal 365 (or count of expected execution days)
```

**Failure investigation (full population review):**
```python
import pandas as pd
df = pd.read_csv('job_logs.csv')
failures = df[df['status'].isin(['FAILED', 'ERROR', 'ABORTED'])]
print(f"Failed jobs in period: {len(failures)}")
# Verify each has corresponding incident ticket
```

---

## 9. Inbound Population File Receipt Protocol

Run this on every population file at receipt:

```bash
#!/bin/bash
# /nopec_2025/shared/scripts/receive_population.sh
FILE="$1"
CONTROL_REF="$2"
RECEIVED_FROM="$3"

echo "================================================================================"
echo "Population Receipt: $(date -Iseconds)"
echo "File: $FILE"
echo "Control: $CONTROL_REF"
echo "Received from: $RECEIVED_FROM"
echo "Size: $(stat -c%s "$FILE") bytes"
echo "SHA-256: $(sha256sum "$FILE" | awk '{print $1}')"
echo "Row count: $(wc -l < "$FILE")"
echo "================================================================================"
```

Append output to `evidence_register.md`.

---

## 10. Exception Handling Protocol

If testing identifies a deviation, do NOT auto-classify. Generate an Exception
Memo containing:

1. **Description:** What occurred, when, who, where
2. **Population context:** "1 of 25 sampled"
3. **Root cause inquiry:** With corroboration noted (do not rely on inquiry alone)
4. **Compensating controls:** Identified and tested separately
5. **Impact assessment:** On the Control Objective
6. **Preliminary classification:** Exception / Deviation / Control Failure
7. **Status flag:** `OPEN — REQUIRES PARTNER ASSESSMENT`

Never finalize an opinion impact in CLI output.

---

## 11. Reviewer Re-Performance Block

Every CLI workpaper must end with a re-performance block:

```
RE-PERFORMANCE INSTRUCTIONS
---------------------------
1. cd /nopec_2025/electric
2. sha256sum -c <(grep "<filename>" evidence_register.md | awk '{print $NF" "$2}')
3. python3 /nopec_2025/shared/scripts/sample_select.py \
       --control CC-LA-03 \
       --seed 20251231 \
       --size 25
4. Compare output to: /nopec_2025/electric/03_samples_selected/CC-LA-03_sample.csv
   Expected SHA-256: <hash>
```

---

## 12. Prohibited Actions

Claude must refuse to:
- Generate fabricated population data represented as real audit evidence
- Modify source files in `01_population_received/`
- Issue an opinion or final conclusion on operating effectiveness
- Translate SOC 1 control failures into SOX materiality language without
  explicit request and `[CROSS-REFERENCE ONLY]` flag
- Bypass IPE validation to expedite sample selection
- Auto-resolve exceptions without partner assessment
- Treat verbal management inquiry as standalone evidence

---

## 13. Standard Bash/Python Building Blocks

```bash
# File integrity
sha256sum file.csv

# Row count (excluding header)
echo $(($(wc -l < file.csv) - 1))

# Date range from a date column (column 3 example)
awk -F',' 'NR>1 {print $3}' file.csv | sort | sed -n '1p;$p'

# Year-over-year control inventory comparison (relevant: 2024 vs. 2025 verification)
diff <(sort 2024_controls.csv) <(sort 2025_controls.csv)

# Find duplicates on a key column
awk -F',' 'NR>1 {print $1}' file.csv | sort | uniq -d
```

```python
# Memory-safe large file read
import pandas as pd
for chunk in pd.read_csv('large.csv', chunksize=100_000):
    pass

# Reproducible sample with seed documentation
df.sample(n=25, random_state=20251231)

# Hash verification post-transformation
import hashlib
with open('file.csv', 'rb') as f:
    print(hashlib.sha256(f.read()).hexdigest())
```

---

## 14. Cross-Year Control Verification

Per engagement note: before distributing 2025 Document Request Lists, verify
whether controls were added, retired, or modified between 2024 and 2025.

```python
import pandas as pd
prior = pd.read_csv('2024_control_inventory.csv')
current = pd.read_csv('2025_control_inventory.csv')

added    = current[~current['control_ref'].isin(prior['control_ref'])]
retired  = prior[~prior['control_ref'].isin(current['control_ref'])]
modified = current.merge(prior, on='control_ref', suffixes=('_25','_24'))
modified = modified[modified['description_25'] != modified['description_24']]

print(f"Added:    {len(added)}")
print(f"Retired:  {len(retired)}")
print(f"Modified: {len(modified)}")
```

Output a `control_inventory_changes.md` memo for partner review before
finalizing the 2025 DRL distribution.

---

*End of CLAUDE.md — NOPEC SOC 1 Engagement*
*This file is a working-paper aid; firm methodology and AICPA standards govern.*

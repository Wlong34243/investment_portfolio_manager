# NOPEC SOC 1 CLI Kit — Deployment Guide

This kit standardizes Claude Code CLI behavior for the NOPEC SOC 1 / SSAE 18
Type II examination covering January 1, 2025 – December 31, 2025.

---

## Files in This Kit

| File | Purpose |
|---|---|
| `CLAUDE.md` | Master operating instructions for Claude Code |
| `evidence_register.md` | Append-only file integrity log (per engagement) |
| `sample_seed_log.md` | Reproducible sample selection documentation |
| `ipe_validation_template.md` | Standardized IPE C&A workpaper |
| `exception_memo_template.md` | Exception evaluation draft form |

---

## Initial Deployment

### 1. Create the engagement directory structure
```bash
mkdir -p /nopec_2025/electric/{01_population_received,02_population_validated,03_samples_selected,04_testing_results,05_evidence,workpapers}
mkdir -p /nopec_2025/gas/{01_population_received,02_population_validated,03_samples_selected,04_testing_results,05_evidence,workpapers}
mkdir -p /nopec_2025/shared/{scripts,templates}
```

### 2. Place CLAUDE.md at the project root
Claude Code reads `CLAUDE.md` from the directory in which it is launched (and
recursively from parent directories). Place it at:

```
/nopec_2025/CLAUDE.md
```

This causes Claude Code to apply the engagement rules automatically whenever
launched from any subdirectory of `/nopec_2025/`.

### 3. Place templates in the shared directory
```
/nopec_2025/shared/templates/ipe_validation_template.md
/nopec_2025/shared/templates/exception_memo_template.md
```

### 4. Initialize the engagement-specific logs
Copy `evidence_register.md` and `sample_seed_log.md` into each service line:

```
/nopec_2025/electric/evidence_register.md
/nopec_2025/electric/sample_seed_log.md
/nopec_2025/gas/evidence_register.md
/nopec_2025/gas/sample_seed_log.md
```

### 5. Set permissions to enforce read-only on received populations
```bash
chmod -R 444 /nopec_2025/electric/01_population_received/
chmod -R 444 /nopec_2025/gas/01_population_received/
```

This prevents accidental modification of source evidence. Apply after each new
population is received and registered.

---

## Daily Workflow

1. **Receive population.** Save to `01_population_received/`. Run the receipt
   protocol script (Section 9 of `CLAUDE.md`). Append entry to
   `evidence_register.md`. Apply read-only permissions.
2. **Validate IPE.** Copy the IPE template to `04_testing_results/`. Complete
   completeness, accuracy, and integrity procedures. Mark hashes verified.
3. **Select sample.** Run the documented Python sample-selection block. Log
   the seed in `sample_seed_log.md`. Save sample to `03_samples_selected/`.
4. **Test operating effectiveness.** Use the workpaper structure from
   `CLAUDE.md` Section 5. Document tickmarks per the legend.
5. **Document exceptions.** If found, copy the exception memo template, mark
   `OPEN — REQUIRES PARTNER ASSESSMENT`.
6. **Reviewer re-performance.** Reviewer follows the re-performance block at
   the end of each workpaper to verify reproducibility.

---

## Notes on Claude Code Behavior

- Claude Code reads `CLAUDE.md` automatically. You do not need to reference it
  in prompts.
- If you want Claude to apply only a subset of the rules (e.g., for an ad-hoc
  task), state the deviation explicitly: "For this task only, skip the IPE
  validation block."
- The CLAUDE.md prohibits fabricated populations and final opinion conclusions.
  These are guardrails, not toggles.

---

## Limitations and Caveats

- This kit is a **working-paper aid**, not firm methodology. In any conflict
  with firm quality control standards, AICPA SOC 1 Reporting Guide, or
  AT-C 205, the authoritative source governs.
- All output remains draft until reviewed by the engagement partner.
- The kit assumes Python 3.8+ with `pandas` available. Adjust per your
  environment.
- Sample size table reflects general AICPA guidance for Type II examinations;
  specific firm methodology may differ.

---

*Maintained for NOPEC SOC 1 2025 examination. Update at each annual rollover.*

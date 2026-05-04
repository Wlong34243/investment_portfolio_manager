"""
Framework Selector — deterministic selection of the appropriate
investment framework for a ticker.

Selection is pure Python, no LLM. The LLM only gets the PRE-COMPUTED
rule results, never the raw rule list. This keeps framework
application auditable: given the same inputs, the same framework
is always selected, and the rule evaluation always produces the
same result.

Position Sizing Extension (Van Tharp):
    call compute_van_tharp_sizing(atr_14, entry_price, portfolio_equity)
    to pre-compute 1R, position_size_units, and trailing_stop before any
    LLM call. The Van Tharp framework JSON lives at:
        vault/frameworks/van_tharp_position_sizing.json
    Agents receive the computed sizing facts; Gemini never computes them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ThesisFrontmatter:
    ticker: str | None = None
    style: str | None = None                  # garp | thematic | boring | etf
    framework_preference: str | None = None   # framework_id
    entry_date: str | None = None
    last_reviewed: str | None = None


def parse_thesis_frontmatter(thesis_text: str) -> ThesisFrontmatter:
    """
    Parse YAML frontmatter from the top of a thesis markdown file.
    Frontmatter is delimited by --- markers. If no frontmatter is
    present, returns an empty ThesisFrontmatter (all None fields).
    Malformed YAML logs a warning and returns an empty frontmatter —
    backward-compatible with unfrontmattered thesis files.
    """
    lines = thesis_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ThesisFrontmatter()
    try:
        end_idx = lines[1:].index("---") + 1
    except ValueError:
        return ThesisFrontmatter()
    yaml_text = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as e:
        logger.warning("Malformed thesis frontmatter: %s", e)
        return ThesisFrontmatter()
    return ThesisFrontmatter(
        ticker=data.get("ticker"),
        style=data.get("style"),
        framework_preference=data.get("framework_preference"),
        entry_date=data.get("entry_date"),
        last_reviewed=data.get("last_reviewed"),
    )


def _check_exclusions(position: dict, framework: dict) -> str | None:
    """
    Return a reason string if the position triggers any of the
    framework's exclusion conditions, else None.
    """
    conditions = framework.get("excludes_conditions", [])
    for condition in conditions:
        if condition == "no_earnings":
            eps = position.get("eps_ttm")
            if eps is not None and eps == 0:
                return "no_earnings: position has zero trailing EPS"
        elif condition == "new_ipo_under_3_years":
            # Treat as always-not-excluded unless we have inception_date data
            logger.debug(
                "Exclusion check 'new_ipo_under_3_years' skipped — no inception_date on position"
            )
        elif condition == "asset_class_is_etf":
            asset_class = (position.get("asset_class") or "").lower()
            if asset_class in ("etf", "fund", "index fund"):
                return f"asset_class_is_etf: position asset_class is '{asset_class}'"
    return None


def select_framework(
    ticker: str,
    position: dict,
    thesis_frontmatter: ThesisFrontmatter,
    frameworks: list[dict],
) -> dict | None:
    """
    Returns the applicable framework dict, or None if no framework applies.

    Selection order:
      a. Only reviewed frameworks (reviewed_by_bill: true).
      b. Explicit frontmatter preference wins if applicable.
      c. Filter by asset class + style + exclusions.
      d. Prefer highest framework_version on ties.
    """
    # a. Filter to reviewed frameworks only
    reviewed = []
    for fw in frameworks:
        if not fw.get("reviewed_by_bill", False):
            logger.info(
                "Skipping unreviewed framework: %s (set reviewed_by_bill: true to enable)",
                fw.get("framework_id", "unknown"),
            )
        else:
            reviewed.append(fw)

    if not reviewed:
        return None

    # b. Explicit frontmatter preference
    if thesis_frontmatter.framework_preference:
        pref_id = thesis_frontmatter.framework_preference
        match = next((fw for fw in reviewed if fw.get("framework_id") == pref_id), None)
        if match:
            exclusion = _check_exclusions(position, match)
            if exclusion:
                logger.warning(
                    "Preferred framework %s excluded for %s: %s — falling through",
                    pref_id, ticker, exclusion,
                )
            else:
                logger.info("Framework selected via frontmatter preference: %s", pref_id)
                return match
        else:
            logger.warning(
                "Frontmatter framework_preference '%s' not found in reviewed frameworks",
                pref_id,
            )

    # c. Filter by asset class, style, exclusions
    asset_class = position.get("asset_class", "")
    style = (thesis_frontmatter.style or "").lower()

    candidates = []
    for fw in reviewed:
        # Asset class match
        applies_to = [a.lower() for a in fw.get("applies_to_asset_classes", [])]
        if asset_class.lower() not in applies_to:
            continue
        # Style match (only if style is known)
        if style:
            fw_styles = [s.lower() for s in fw.get("applies_to_styles", [])]
            if fw_styles and style not in fw_styles:
                continue
        # Exclusion check
        exclusion = _check_exclusions(position, fw)
        if exclusion:
            logger.info(
                "Framework %s excluded for %s: %s",
                fw.get("framework_id"), ticker, exclusion,
            )
            continue
        candidates.append(fw)

    if not candidates:
        return None

    # d. Multiple matches — prefer highest version (string sort for v1)
    if len(candidates) > 1:
        candidates.sort(key=lambda fw: fw.get("framework_version", "0"), reverse=True)
        selected = candidates[0]
        rejected = [fw.get("framework_id") for fw in candidates[1:]]
        logger.info(
            "Multiple frameworks matched %s; selected %s, rejected %s",
            ticker, selected.get("framework_id"), rejected,
        )
        return selected

    logger.info("Framework selected: %s for %s", candidates[0].get("framework_id"), ticker)
    return candidates[0]


def evaluate_framework_rules(
    position: dict,
    fundamentals: dict,
    framework: dict,
) -> dict:
    """
    Evaluate each rule in the framework against the position's fundamentals.
    Returns a dict matching the FrameworkValidation Pydantic schema.
    Pure Python — no LLM call.
    """
    rules_evaluated = []
    insufficient_data_rules = []
    required_passed = 0
    required_total = 0
    preferred_passed = 0
    preferred_total = 0

    for rule in framework.get("rules", []):
        rule_id = rule["rule_id"]
        severity = rule.get("severity", "preferred")
        description = rule.get("description", "")
        required_fields = rule.get("required_fields", [])
        check_type = rule.get("check_type", "")

        if severity == "required":
            required_total += 1
        else:
            preferred_total += 1

        # Check for missing fields
        missing_fields = [f for f in required_fields if fundamentals.get(f) is None]
        if missing_fields:
            insufficient_data_rules.append(rule_id)
            rules_evaluated.append({
                "rule_id": rule_id,
                "description": description,
                "passed": None,
                "observed_value": None,
                "severity": severity,
                "rationale": f"Missing field(s): {', '.join(missing_fields)}",
            })
            continue

        # Get the primary value (first required field)
        value = fundamentals.get(required_fields[0])
        observed_value = str(value) if value is not None else None

        passed = None
        rationale = ""
        interp = rule.get("interpretation", {})

        if check_type == "range":
            t_min = rule.get("target_min")
            t_max = rule.get("target_max")
            if t_min is not None and t_max is not None:
                if t_min <= value <= t_max:
                    passed = True
                    rationale = interp.get("pass", f"{value} is within [{t_min}, {t_max}]")
                elif value < t_min:
                    passed = False
                    rationale = interp.get("fail_low", f"{value} is below minimum {t_min}")
                else:
                    passed = False
                    rationale = interp.get("fail_high", f"{value} is above maximum {t_max}")

        elif check_type == "threshold_max":
            t_max = rule.get("target_max")
            if t_max is not None:
                passed = value <= t_max
                rationale = (
                    interp.get("pass", f"{value} <= {t_max}") if passed
                    else interp.get("fail", f"{value} > {t_max}")
                )

        elif check_type == "threshold_min":
            t_min = rule.get("target_min")
            if t_min is not None:
                passed = value >= t_min
                rationale = (
                    interp.get("pass", f"{value} >= {t_min}") if passed
                    else interp.get("fail", f"{value} < {t_min}")
                )

        elif check_type == "equal":
            target = rule.get("target_value")
            passed = value == target
            rationale = (
                interp.get("pass", f"{value} == {target}") if passed
                else interp.get("fail", f"{value} != {target}")
            )

        rules_evaluated.append({
            "rule_id": rule_id,
            "description": description,
            "passed": passed,
            "observed_value": observed_value,
            "severity": severity,
            "rationale": rationale,
        })

        if passed is True:
            if severity == "required":
                required_passed += 1
            else:
                preferred_passed += 1

    threshold = framework.get("passing_threshold", {})
    req_min = threshold.get("required_rules_passed_minimum", 0)
    pref_min = threshold.get("preferred_rules_passed_minimum", 0)
    passes_framework = (required_passed >= req_min) and (preferred_passed >= pref_min)

    framework_score_display = (
        f"{required_passed}/{required_total} required + "
        f"{preferred_passed}/{preferred_total} preferred"
    )

    return {
        "framework_id": framework["framework_id"],
        "framework_version": framework["framework_version"],
        "framework_content_sha256": framework.get("_framework_content_sha256", ""),
        "applicable": True,
        "applicability_rationale": (
            f"Framework {framework['framework_id']} selected for {position.get('ticker', '?')} "
            f"based on asset class and style match."
        ),
        "rules_evaluated": rules_evaluated,
        "required_rules_passed": required_passed,
        "required_rules_total": required_total,
        "preferred_rules_passed": preferred_passed,
        "preferred_rules_total": preferred_total,
        "passes_framework": passes_framework,
        "insufficient_data_rules": insufficient_data_rules,
        "framework_score_display": framework_score_display,
    }


# ---------------------------------------------------------------------------
# Van Tharp position sizing (pure Python — never delegated to LLM)
# ---------------------------------------------------------------------------

def compute_van_tharp_sizing(
    atr_14: float,
    entry_price: float,
    portfolio_equity: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 3.0,
) -> dict:
    """
    Compute Van Tharp R-multiple position sizing from ATR data.

    All arithmetic is pure Python — results are passed as facts to agents;
    Gemini NEVER computes these values.

    Source framework: vault/frameworks/van_tharp_position_sizing.json
    ATR source:       composite["calculated_technical_stops"] (from tasks/enrich_atr.py)

    Note on multipliers:
      - enrich_atr.py uses 2.5x ATR for the protective stop (portfolio risk management).
      - Van Tharp uses 3.0x ATR for 1R (position sizing baseline). These are different
        concepts: the protective stop is a portfolio-level trigger; 1R is the per-trade
        sizing unit.

    Args:
        atr_14:          14-day Average True Range in dollars (from calculated_technical_stops).
        entry_price:     Current price or intended entry price in dollars.
        portfolio_equity: Total liquid portfolio value in dollars.
        risk_pct:        Fraction of portfolio equity to risk per trade (default: 1% = 0.01).
        atr_multiplier:  ATR multiplier for 1R calculation (default: 3.0 per Van Tharp).

    Returns dict with:
        per_share_risk_1r:   Dollar risk per share (1R = ATR × multiplier).
        stop_loss_price:     Entry price minus 1R (long position stop).
        trailing_stop_price: Same as stop_loss_price at initiation; moves up as price rises.
        total_allowable_risk_usd: portfolio_equity × risk_pct.
        position_size_units: Number of shares/units to buy = total_risk / per_share_risk_1r.
        position_size_usd:   Dollar value of the position at entry = units × entry_price.
        r_multiple_at_target: Pre-computed for common 2R and 3R profit targets.
        sizing_valid:        False if inputs are invalid (zero ATR, zero price, etc.).
    """
    if atr_14 <= 0 or entry_price <= 0 or portfolio_equity <= 0:
        return {
            "per_share_risk_1r": 0.0,
            "stop_loss_price": 0.0,
            "trailing_stop_price": 0.0,
            "total_allowable_risk_usd": 0.0,
            "position_size_units": 0,
            "position_size_usd": 0.0,
            "r_multiple_at_target": {"2R": 0.0, "3R": 0.0},
            "sizing_valid": False,
            "note": "Invalid inputs: ATR, entry_price, and portfolio_equity must all be > 0.",
        }

    per_share_risk_1r      = round(atr_14 * atr_multiplier, 4)
    stop_loss_price        = round(entry_price - per_share_risk_1r, 4)
    trailing_stop_price    = stop_loss_price  # at initiation; agent notes it moves up
    total_allowable_risk   = round(portfolio_equity * risk_pct, 2)
    position_size_units    = int(total_allowable_risk / per_share_risk_1r) if per_share_risk_1r > 0 else 0
    position_size_usd      = round(position_size_units * entry_price, 2)

    return {
        "per_share_risk_1r":         per_share_risk_1r,
        "stop_loss_price":           stop_loss_price,
        "trailing_stop_price":       trailing_stop_price,
        "total_allowable_risk_usd":  total_allowable_risk,
        "position_size_units":       position_size_units,
        "position_size_usd":         position_size_usd,
        "r_multiple_at_target": {
            "2R": round(entry_price + 2 * per_share_risk_1r, 4),
            "3R": round(entry_price + 3 * per_share_risk_1r, 4),
        },
        "sizing_valid": True,
        "inputs": {
            "atr_14": atr_14,
            "entry_price": entry_price,
            "portfolio_equity": portfolio_equity,
            "risk_pct": risk_pct,
            "atr_multiplier": atr_multiplier,
        },
    }

"""Tests for utils/agents/ai_research_analyst.py."""

from __future__ import annotations

from utils.agents.ai_research_analyst import AIResearchBrief, validate_brief


def test_schema_has_no_allocation_fields():
    fields = set(AIResearchBrief.model_fields)
    forbidden = {f for f in fields if any(x in f.lower() for x in ("alloc", "target_pct", "weight"))}
    assert not forbidden


def test_validate_rule2_true_positive():
    bad = {
        "headline": "x",
        "summary": "this is bullish for NVDA, go long",
        "claims": [],
        "named_systems": [],
        "named_orgs": ["Nvidia"],
        "benchmarks": [],
        "open_questions": [],
        "novelty": "commentary",
        "source_quality": "Low",
    }
    v = validate_brief(bad)
    assert any("rule 2" in x for x in v)


def test_validate_rule2_false_positive_long_context():
    ok = {
        "headline": "Scaling",
        "summary": "The model supports a long context window and short training run.",
        "claims": [{"claim": "long context window", "claim_type": "capability", "specificity": "qualitative", "attributed_to": ""}],
        "named_systems": [],
        "named_orgs": [],
        "benchmarks": [],
        "open_questions": [],
        "novelty": "explainer",
        "source_quality": "Medium",
    }
    v = validate_brief(ok)
    assert not any("rule 2" in x for x in v)


def test_validate_rule2_false_positive_long_near_ai_acronym():
    ok = {
        "headline": "Long context for AI agents",
        "summary": "Agents need long memory over AI tool chains.",
        "claims": [{"claim": "long context helps AI coding", "claim_type": "capability", "specificity": "qualitative", "attributed_to": ""}],
        "named_systems": [],
        "named_orgs": [],
        "benchmarks": [],
        "open_questions": [],
        "novelty": "explainer",
        "source_quality": "Medium",
    }
    v = validate_brief(ok)
    assert not any("rule 2" in x for x in v)


def test_validate_forbidden_alloc_key():
    bad = {
        "headline": "x",
        "summary": "y",
        "target_allocations": [],
        "claims": [{"claim": "a", "claim_type": "capability", "specificity": "qualitative", "attributed_to": ""}],
        "named_systems": [],
        "named_orgs": [],
        "benchmarks": [],
        "open_questions": [],
        "novelty": "explainer",
        "source_quality": "Medium",
    }
    v = validate_brief(bad)
    assert any("rule 1" in x for x in v)

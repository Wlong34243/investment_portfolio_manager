from core.analyst.plan import plan_question


def test_mu_buy_plan_templates():
    plan = plan_question("when did I first buy MU and what was the reasoning")
    assert "MU" in plan.tickers
    assert "position_transactions" in plan.template_ids
    assert plan.corpus_queries


def test_weather_empty_plan():
    plan = plan_question("what's the weather")
    assert plan.is_empty


def test_has_not_ticker_false_positive():
    plan = plan_question("what has been said about ET's Lake Charles project")
    assert plan.tickers == ["ET"]
    assert len(plan.corpus_queries) >= 3
    assert any("lake charles" in cq.query for cq in plan.corpus_queries)

from src.services.query_planner import QueryPlanner


def test_query_planner_expands_environment_terms_deterministically() -> None:
    planner = QueryPlanner()
    signals = [
        {"indicator_name": "PM 2.5 concentration"},
        {"indicator_name": "Waste disposal coverage"},
    ]

    plan_a = planner.build_retrieval_plan(
        municipality_id="srb-belgrade",
        category="Environment",
        year=2024,
        priority_signals=signals,
        top_k=8,
    )
    plan_b = planner.build_retrieval_plan(
        municipality_id="srb-belgrade",
        category="Environment",
        year=2024,
        priority_signals=signals,
        top_k=8,
    )

    assert plan_a.model_dump(mode="json") == plan_b.model_dump(mode="json")
    assert "air quality" in plan_a.query_terms["must_have"]
    assert "PM 2.5 concentration" in plan_a.query_terms["must_have"]

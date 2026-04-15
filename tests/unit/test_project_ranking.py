from src.ranking.project_filters import ProjectFilter
from src.ranking.project_scorer import ProjectScorer
from src.ranking.project_selector import ProjectSelector
from src.schemas.domain import EvidenceBundle, EvidenceItem, PrioritySignal, RecommendationCandidate
from src.storage.projects import InMemoryProjectRepository


def test_project_filter_marks_exclusions_and_missing_information() -> None:
    repository = InMemoryProjectRepository()
    project_filter = ProjectFilter()

    filtered = project_filter.filter_projects(
        projects=repository.list_by_category("Environment"),
        municipality_id="srb-belgrade",
        category="Environment",
    )

    excluded = {item.project.project_id: item for item in filtered if item.exclusion_reasons}
    assert "proj-004" in excluded
    assert "municipality_mismatch" in excluded["proj-004"].exclusion_reasons
    assert "inactive_project_status" in excluded["proj-004"].exclusion_reasons


def test_project_scorer_builds_breakdowns_and_matches_candidate() -> None:
    repository = InMemoryProjectRepository()
    project_filter = ProjectFilter()
    scorer = ProjectScorer()
    filtered = project_filter.filter_projects(
        projects=repository.list_by_category("Environment"),
        municipality_id="srb-belgrade",
        category="Environment",
    )

    scored = scorer.score_projects(
        filtered_projects=filtered,
        recommendation_candidates=[
            RecommendationCandidate(
                candidate_id="cand-1",
                title="Air Quality Monitoring Upgrade",
                summary="Expand municipal air monitoring.",
                problem_statement="Air quality remains below target.",
                intended_outcome="Reduce pollution exposure.",
                category="Environment",
                public_investment_type="capital_program",
                supporting_evidence_ids=["analytics:air-quality", "local:policy-1"],
                confidence=0.9,
                caveats=[],
            )
        ],
        priority_signals=[
            PrioritySignal(
                indicator_id="air-quality",
                indicator_name="Air Quality",
                severity=0.85,
                reason="Large municipal performance gap.",
            )
        ],
        evidence_bundle=EvidenceBundle(
            bundle_id="bundle-1",
            municipality_id="srb-belgrade",
            category="Environment",
            items=[
                EvidenceItem(
                    evidence_id="analytics:air-quality",
                    origin="analytics",
                    statement="Air quality is underperforming.",
                    confidence=0.92,
                ),
                EvidenceItem(
                    evidence_id="local:policy-1",
                    origin="local_retrieval",
                    statement="Policy supports monitoring expansion.",
                    confidence=0.88,
                ),
            ],
        ),
        municipality_id="srb-belgrade",
    )

    best = sorted(
        [item for item in scored if not item.exclusion_reasons],
        key=lambda item: (-item.total_score, item.project_id),
    )[0]
    assert best.project_id == "proj-001"
    assert best.matched_candidate_id == "cand-1"
    assert best.ranking_breakdown.indicator_alignment > 0
    assert best.ranking_breakdown.evidence_support_strength > 0


def test_project_selector_is_deterministic_and_skips_excluded_projects() -> None:
    repository = InMemoryProjectRepository()
    project_filter = ProjectFilter()
    scorer = ProjectScorer()
    selector = ProjectSelector()
    filtered = project_filter.filter_projects(
        projects=repository.list_by_category("Environment"),
        municipality_id="srb-belgrade",
        category="Environment",
    )
    scored = scorer.score_projects(
        filtered_projects=filtered,
        recommendation_candidates=[
            RecommendationCandidate(
                candidate_id="cand-1",
                title="Waste Logistics Modernization",
                summary="Modernize waste transfer operations.",
                problem_statement="Waste collection performance is uneven.",
                intended_outcome="Improve sanitation service quality.",
                category="Environment",
                public_investment_type="capital_program",
                supporting_evidence_ids=["analytics:waste"],
                confidence=0.8,
                caveats=[],
            )
        ],
        priority_signals=[
            PrioritySignal(
                indicator_id="waste",
                indicator_name="Waste Collection",
                severity=0.82,
                reason="Persistent waste-management gap.",
            )
        ],
        evidence_bundle=EvidenceBundle(
            bundle_id="bundle-2",
            municipality_id="srb-belgrade",
            category="Environment",
            items=[
                EvidenceItem(
                    evidence_id="analytics:waste",
                    origin="analytics",
                    statement="Waste indicators are under target.",
                    confidence=0.9,
                )
            ],
        ),
        municipality_id="srb-belgrade",
    )

    selected_a, excluded_a = selector.select_projects(scored_projects=scored, top_n=2)
    selected_b, excluded_b = selector.select_projects(scored_projects=scored, top_n=2)

    assert [item.project_id for item in selected_a] == [item.project_id for item in selected_b]
    assert [item.project_id for item in excluded_a] == [item.project_id for item in excluded_b]
    assert all(not item.exclusion_reasons for item in selected_a)
    assert any(item.project_id == "proj-004" for item in excluded_a)

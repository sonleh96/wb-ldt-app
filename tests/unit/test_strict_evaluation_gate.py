from src.schemas.workflow import ContextPack, EvidenceCard
from src.validation.strict_gate import StrictEvaluationGate


def _card(provenance_complete: bool, score: float) -> EvidenceCard:
    return EvidenceCard(
        card_id="c1",
        source_id="s1",
        chunk_id="k1",
        source_type="policy_document",
        relevance_score=score,
        selection_reason="test",
        claim_text="claim",
        supporting_excerpt="excerpt",
        municipality_id="srb-belgrade",
        category="Environment",
        provenance_complete=provenance_complete,
    )


def test_strict_gate_fails_on_missing_provenance() -> None:
    gate = StrictEvaluationGate()
    pack = ContextPack(
        run_id="r1",
        cards=[_card(False, 0.3)],
        max_cards=8,
        token_budget_per_card=120,
        provenance_completeness_ratio=0.0,
    )
    report = gate.evaluate(
        context_pack=pack,
        selected_projects=[{"title": "P1"}],
        explanation="P1 is selected",
        retrieval_diagnostics={"returned_result_count": 1},
    )
    assert report.status == "failed"
    assert "provenance_completeness" in report.failed_checks


def test_strict_gate_fails_on_low_relevance() -> None:
    gate = StrictEvaluationGate()
    pack = ContextPack(
        run_id="r2",
        cards=[_card(True, 0.001)],
        max_cards=8,
        token_budget_per_card=120,
        provenance_completeness_ratio=1.0,
    )
    report = gate.evaluate(
        context_pack=pack,
        selected_projects=[{"title": "P1"}],
        explanation="P1 is selected",
        retrieval_diagnostics={"returned_result_count": 1},
    )
    assert report.status == "failed"
    assert "retrieval_relevance" in report.failed_checks

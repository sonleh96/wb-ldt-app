from src.observability.tracing import RunTrace, RunTraceRecorder
from src.schemas.domain import ProjectReview
from src.schemas.run_state import RunRecord, RunState
from src.storage.project_reviews import PostgresProjectReviewStore, ProjectReviewRecord, utcnow as review_utcnow
from src.storage.run_store import PostgresRunStore
from src.storage.run_traces import PostgresRunTraceStore
from tests.unit.fake_psycopg import FakePostgresDatabase, FakePsycopg


def test_postgres_runtime_stores_round_trip_records(monkeypatch) -> None:
    fake_psycopg = FakePsycopg(FakePostgresDatabase())
    monkeypatch.setattr("src.storage.run_store.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.project_reviews.psycopg", fake_psycopg)
    monkeypatch.setattr("src.storage.run_traces.psycopg", fake_psycopg)

    run_store = PostgresRunStore(database_url="postgresql://fake")
    review_store = PostgresProjectReviewStore(database_url="postgresql://fake")
    trace_store = PostgresRunTraceStore(database_url="postgresql://fake")

    run = RunRecord(
        run_id="run-1",
        request={"municipality_id": "srb-belgrade", "category": "Environment", "year": 2024},
        state=RunState.RUNNING,
        current_node="retrieve_local_evidence",
    )
    run_store.create(run)
    updated_run = run.model_copy(update={"state": RunState.COMPLETED, "result": {"validation_summary": "passed"}})
    run_store.update(updated_run)

    stored_run = run_store.get("run-1")
    assert stored_run is not None
    assert stored_run.state == RunState.COMPLETED
    assert stored_run.result["validation_summary"] == "passed"
    assert run_store.list_runs()

    review_record = ProjectReviewRecord(
        run_id="run-1",
        project_id="proj-001",
        include_web_evidence=False,
        review=ProjectReview(
            project_id="proj-001",
            summary="Suitable for follow-up.",
            municipality_relevance="Fits Belgrade.",
            readiness="Moderate",
            financing_signals="Plausible",
            implementation_considerations=["Sequence procurement."],
            risks_and_caveats=["Evidence remains limited."],
            citation_ids=["review:proj-001:1"],
        ),
        validation_summary="passed",
        evidence_ids=["review:proj-001:1"],
        cached_at=review_utcnow(),
    )
    review_store.upsert(review_record)
    stored_review = review_store.get(run_id="run-1", project_id="proj-001", include_web_evidence=False)
    assert stored_review is not None
    assert stored_review.review.project_id == "proj-001"

    recorder = RunTraceRecorder(store=trace_store)
    recorder.start_run(run_id="run-1", route=["create_run", "finalize_run"])
    recorder.record_failure(run_id="run-1", node_name="finalize_run", message="synthetic")
    stored_trace = trace_store.get("run-1")
    assert stored_trace is not None
    assert stored_trace.route == ["create_run", "finalize_run"]
    assert stored_trace.failure == {"node_name": "finalize_run", "message": "synthetic"}

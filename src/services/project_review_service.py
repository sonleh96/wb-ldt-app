"""Project review workflow orchestration and caching."""

from __future__ import annotations

from dataclasses import asdict

from src.core.errors import AppError
from src.llm.project_review_generator import ProjectReviewGenerator
from src.schemas.api import ProjectReviewResponse
from src.schemas.run_state import RunState
from src.retrieval.service import RetrievalService
from src.services.run_registry import RunRegistry
from src.storage.project_reviews import ProjectReviewRecord, ProjectReviewStore, utcnow
from src.storage.projects import ProjectRepository


class ProjectReviewService:
    """Generate and cache structured project reviews for completed recommendation runs."""

    def __init__(
        self,
        *,
        run_registry: RunRegistry,
        project_repository: ProjectRepository,
        retrieval_service: RetrievalService,
        project_review_store: ProjectReviewStore,
        project_review_generator: ProjectReviewGenerator,
    ) -> None:
        """Initialize the service."""

        self._run_registry = run_registry
        self._project_repository = project_repository
        self._retrieval_service = retrieval_service
        self._project_review_store = project_review_store
        self._project_review_generator = project_review_generator

    def get_or_create_review(
        self,
        *,
        run_id: str,
        project_id: str,
        include_web_evidence: bool,
    ) -> ProjectReviewResponse:
        """Return a cached review or build a new one."""

        cached = self._project_review_store.get(
            run_id=run_id,
            project_id=project_id,
            include_web_evidence=include_web_evidence,
        )
        if cached:
            return ProjectReviewResponse(
                run_id=run_id,
                project_review=cached.review,
                validation_summary=cached.validation_summary,
            )

        run = self._run_registry.get_run(run_id)
        if run.state != RunState.COMPLETED:
            raise AppError(
                status_code=409,
                code="run_not_completed",
                message=f"Run {run_id} is not completed.",
                metadata={"state": run.state.value},
            )

        selected_project = next(
            (item for item in run.result.get("selected_projects", []) if item.get("project_id") == project_id),
            None,
        )
        if selected_project is None:
            raise AppError(
                status_code=404,
                code="project_not_in_run",
                message=f"Project {project_id} was not selected in run {run_id}.",
                target="project_id",
            )

        project_record = next(
            (item for item in self._project_repository.list_by_category(str(run.request.get("category", ""))) if item.project_id == project_id),
            None,
        )
        if project_record is None:
            raise AppError(
                status_code=404,
                code="project_not_found",
                message=f"Project {project_id} was not found.",
                target="project_id",
            )

        review_evidence = self._build_review_evidence(
            run_id=run_id,
            project_id=project_id,
            project_title=project_record.title,
            municipality_id=str(run.request.get("municipality_id", "")),
            category=str(run.request.get("category", "")),
            include_web_evidence=include_web_evidence,
        )
        review = self._project_review_generator.generate(
            run_context={
                "run_id": run_id,
                "municipality_id": str(run.request.get("municipality_id", "")),
                "category": str(run.request.get("category", "")),
                "year": int(run.request.get("year", 0)),
                "selected_project": selected_project,
            },
            project={
                **asdict(project_record),
                "selected_project": selected_project,
            },
            review_evidence=review_evidence,
        )
        record = self._project_review_store.upsert(
            ProjectReviewRecord(
                run_id=run_id,
                project_id=project_id,
                include_web_evidence=include_web_evidence,
                review=review,
                validation_summary="passed" if review.citation_ids else "warning",
                evidence_ids=[item["evidence_id"] for item in review_evidence],
                cached_at=utcnow(),
            )
        )
        return ProjectReviewResponse(
            run_id=run_id,
            project_review=record.review,
            validation_summary=record.validation_summary,
        )

    def _build_review_evidence(
        self,
        *,
        run_id: str,
        project_id: str,
        project_title: str,
        municipality_id: str,
        category: str,
        include_web_evidence: bool,
    ) -> list[dict[str, object]]:
        """Build a compact evidence list for project review generation."""

        response = self._retrieval_service.search(
            query=project_title,
            mode="hybrid",
            top_k=4,
            municipality_id=municipality_id,
            category=category,
        )
        evidence = [
            {
                "evidence_id": f"review:{project_id}:{index + 1}",
                "source_id": result.source_id,
                "chunk_id": result.chunk_id,
                "statement": result.snippet,
                "citation_uri": result.citation_uri,
                "source_type": result.source_type,
            }
            for index, result in enumerate(response.results)
        ]
        if include_web_evidence:
            evidence.append(
                {
                    "evidence_id": f"review-web:{run_id}:{project_id}",
                    "source_id": "web-placeholder",
                    "chunk_id": "web-placeholder",
                    "statement": (
                        "Policy-controlled web evidence placeholder. Dedicated live web enrichment remains pending."
                    ),
                    "citation_uri": None,
                    "source_type": "web_source",
                }
            )
        if not evidence:
            raise AppError(
                status_code=422,
                code="project_review_evidence_missing",
                message=f"No review evidence was found for project {project_id}.",
            )
        return evidence

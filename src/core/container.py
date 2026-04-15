"""Core application bootstrap, middleware, logging, and error handling."""

from pathlib import Path

from src.config.settings import Settings, get_settings
from src.embeddings import EmbeddingClient, build_embedding_client
from src.ingestion.chunking import SemanticChunkingConfig
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.source_registry import SourceRegistry
from src.llm.explanation_generator import ExplanationGenerator
from src.llm.project_review_generator import ProjectReviewGenerator
from src.llm.recommendation_generator import RecommendationGenerator
from src.observability.tracing import RunTraceRecorder
from src.retrieval.context_windows import RetrievalContextWindowExpander
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.semantic import SemanticRetriever
from src.retrieval.service import RetrievalService
from src.services.context_packer import ContextPacker
from src.services.evidence_bundle import EvidenceBundleService
from src.services.municipality_profile_service import MunicipalityProfileService
from src.services.project_review_service import ProjectReviewService
from src.services.query_planner import QueryPlanner
from src.services.run_inspection_service import RunInspectionService
from src.services.run_registry import RunRegistry
from src.services.source_admin_service import SourceAdminService
from src.services.workflow_launcher import RecommendationWorkflowLauncher
from src.storage.indicators import InMemoryIndicatorRepository
from src.storage.municipalities import InMemoryMunicipalityRepository
from src.storage.project_reviews import (
    InMemoryProjectReviewStore,
    PostgresProjectReviewStore,
    ProjectReviewStore,
)
from src.storage.postgres_sources import PostgresSourceRepository
from src.storage.projects import InMemoryProjectRepository
from src.storage.run_store import InMemoryRunStore, PostgresRunStore, RunStore
from src.storage.run_traces import InMemoryRunTraceStore, PostgresRunTraceStore, RunTraceStore
from src.storage.sources import InMemorySourceRepository, SourceRepository
from src.validation.run_validator import RunValidator
from src.validation.strict_gate import StrictEvaluationGate
from src.workflows.nodes.recommendation_nodes import RecommendationNodes
from src.workflows.recommendation_graph import RecommendationGraph


class ServiceContainer:
    """Class representing ServiceContainer."""
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        recommendation_generator: RecommendationGenerator | None = None,
        explanation_generator: ExplanationGenerator | None = None,
        project_review_generator: ProjectReviewGenerator | None = None,
        embedding_client: EmbeddingClient | None = None,
        source_repository: SourceRepository | None = None,
        run_store: RunStore | None = None,
        project_review_store: ProjectReviewStore | None = None,
        run_trace_store: RunTraceStore | None = None,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self.settings = settings or get_settings()
        self.municipality_repository = InMemoryMunicipalityRepository()
        self.indicator_repository = InMemoryIndicatorRepository()
        self.project_repository = InMemoryProjectRepository()

        self.municipality_profile_service = MunicipalityProfileService(
            municipality_repository=self.municipality_repository,
            indicator_repository=self.indicator_repository,
        )

        self.embedding_client = embedding_client or build_embedding_client(self.settings)
        self.chunking_config = SemanticChunkingConfig(
            max_tokens=self.settings.semantic_chunk_max_tokens,
            overlap_tokens=self.settings.semantic_chunk_overlap_tokens,
            min_chunk_tokens=self.settings.semantic_chunk_min_tokens,
            breakpoint_threshold_type=self.settings.semantic_chunk_breakpoint_type,
            breakpoint_threshold_amount=self.settings.semantic_chunk_breakpoint_amount,
        )

        if source_repository is not None:
            self.source_repository = source_repository
        elif self.settings.storage_backend.lower() == "postgres":
            if not self.settings.database_url:
                raise ValueError("LDT_DATABASE_URL is required when storage_backend=postgres")
            self.source_repository = PostgresSourceRepository(
                database_url=self.settings.database_url,
                embedding_dimensions=self.settings.embedding_dimensions,
            )
        else:
            self.source_repository = InMemorySourceRepository()
        self.source_registry = SourceRegistry(self.source_repository)
        self.ingestion_pipeline = IngestionPipeline(
            self.source_repository,
            embedding_client=self.embedding_client,
            chunking_config=self.chunking_config,
        )

        self.source_admin_service = SourceAdminService(
            source_registry=self.source_registry,
            ingestion_pipeline=self.ingestion_pipeline,
        )

        if self.settings.auto_seed_sources:
            self._seed_sources()

        self.semantic_retriever = SemanticRetriever(self.source_repository, self.embedding_client)
        self.lexical_retriever = LexicalRetriever(self.source_repository)
        self.hybrid_retriever = HybridRetriever(
            lexical_retriever=self.lexical_retriever,
            semantic_retriever=self.semantic_retriever,
        )
        self.context_window_expander = RetrievalContextWindowExpander(
            self.source_repository,
            neighbor_window=self.settings.retrieval_context_window_neighbors,
        )
        self.retrieval_service = RetrievalService(
            semantic_retriever=self.semantic_retriever,
            lexical_retriever=self.lexical_retriever,
            hybrid_retriever=self.hybrid_retriever,
            context_window_expander=self.context_window_expander,
        )
        self.evidence_bundle_service = EvidenceBundleService()
        self.query_planner = QueryPlanner()
        self.context_packer = ContextPacker()
        self.strict_evaluation_gate = StrictEvaluationGate()
        self.run_validator = RunValidator()
        self.recommendation_generator = recommendation_generator or RecommendationGenerator.from_settings(
            self.settings
        )
        self.explanation_generator = explanation_generator or ExplanationGenerator.from_settings(self.settings)
        self.project_review_generator = project_review_generator or ProjectReviewGenerator.from_settings(
            self.settings
        )

        self.run_store = run_store or self._build_run_store()
        self.project_review_store = project_review_store or self._build_project_review_store()
        self.run_trace_store = run_trace_store or self._build_run_trace_store()
        self.run_trace_recorder = RunTraceRecorder(store=self.run_trace_store)
        self.run_registry = RunRegistry(self.run_store)
        self.run_inspection_service = RunInspectionService(
            run_registry=self.run_registry,
            run_trace_recorder=self.run_trace_recorder,
        )
        self.project_review_service = ProjectReviewService(
            run_registry=self.run_registry,
            project_repository=self.project_repository,
            retrieval_service=self.retrieval_service,
            project_review_store=self.project_review_store,
            project_review_generator=self.project_review_generator,
        )
        self.workflow_nodes = RecommendationNodes(
            municipality_profile_service=self.municipality_profile_service,
            retrieval_service=self.retrieval_service,
            evidence_bundle_service=self.evidence_bundle_service,
            project_repository=self.project_repository,
            query_planner=self.query_planner,
            context_packer=self.context_packer,
            strict_evaluation_gate=self.strict_evaluation_gate,
            run_validator=self.run_validator,
            recommendation_generator=self.recommendation_generator,
            explanation_generator=self.explanation_generator,
        )
        self.recommendation_graph = RecommendationGraph(
            run_registry=self.run_registry,
            nodes=self.workflow_nodes,
            run_trace_recorder=self.run_trace_recorder,
        )
        self.workflow_launcher = RecommendationWorkflowLauncher(self.recommendation_graph)

    def _build_run_store(self) -> RunStore:
        """Return the configured run store implementation."""

        if self.settings.storage_backend.lower() == "postgres":
            if not self.settings.database_url:
                raise ValueError("LDT_DATABASE_URL is required when storage_backend=postgres")
            return PostgresRunStore(database_url=self.settings.database_url)
        return InMemoryRunStore()

    def _build_project_review_store(self) -> ProjectReviewStore:
        """Return the configured project-review store implementation."""

        if self.settings.storage_backend.lower() == "postgres":
            if not self.settings.database_url:
                raise ValueError("LDT_DATABASE_URL is required when storage_backend=postgres")
            return PostgresProjectReviewStore(database_url=self.settings.database_url)
        return InMemoryProjectReviewStore()

    def _build_run_trace_store(self) -> RunTraceStore:
        """Return the configured run-trace store implementation."""

        if self.settings.storage_backend.lower() == "postgres":
            if not self.settings.database_url:
                raise ValueError("LDT_DATABASE_URL is required when storage_backend=postgres")
            return PostgresRunTraceStore(database_url=self.settings.database_url)
        return InMemoryRunTraceStore()

    def _seed_sources(self) -> None:
        """Internal helper to seed sources."""
        root = Path(__file__).resolve().parents[2]
        policy_path = root / "docs" / "seed_environment_policy.txt"
        dataset_path = root / "docs" / "seed_environment_dataset.csv"

        policy_source = self.source_registry.register_source(
            source_type="policy_document",
            title="Belgrade Environment Policy Seed",
            uri=str(policy_path),
            municipality_id="srb-belgrade",
            category="Environment",
            mime_type="text/plain",
        )
        dataset_source = self.source_registry.register_source(
            source_type="dataset",
            title="Belgrade Environment Dataset Seed",
            uri=str(dataset_path),
            municipality_id="srb-belgrade",
            category="Environment",
            mime_type="text/csv",
        )

        self.ingestion_pipeline.ingest_source(policy_source.source_id)
        self.ingestion_pipeline.ingest_source(dataset_source.source_id)

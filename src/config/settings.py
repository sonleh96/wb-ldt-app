"""Configuration loading and application settings."""

from functools import lru_cache

from pydantic import Field
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:  # pragma: no cover - compatibility for lean test environments
    from pydantic import BaseModel

    class BaseSettings(BaseModel):  # type: ignore[misc]
        """Fallback settings base when pydantic-settings is unavailable."""

        def __init__(self, **data):
            """Initialize the instance and its dependencies."""
            super().__init__(**data)

    def SettingsConfigDict(**kwargs):  # type: ignore[misc]
        """Return a passthrough mapping for fallback BaseSettings."""
        return kwargs


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LDT_", case_sensitive=False)

    environment: str = Field(default="dev")
    app_name: str = Field(default="ldt-de-v2")
    app_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")
    admin_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4.1-mini")
    openai_base_url: str | None = Field(default=None)
    embedding_provider: str = Field(default="local")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=256)
    chunking_strategy: str = Field(default="semantic")
    semantic_chunk_max_tokens: int = Field(default=180)
    semantic_chunk_overlap_tokens: int = Field(default=24)
    semantic_chunk_min_tokens: int = Field(default=40)
    semantic_chunk_breakpoint_type: str = Field(default="percentile")
    semantic_chunk_breakpoint_amount: float = Field(default=90.0)
    retrieval_context_window_neighbors: int = Field(default=1)
    storage_backend: str = Field(default="memory")
    database_url: str | None = Field(default=None)
    document_store_backend: str = Field(default="local")
    gcp_project: str | None = Field(default=None)
    gcs_bucket: str | None = Field(default=None)
    gcs_prefix: str = Field(default="ldt/sources")
    serbia_dataset_loading_enabled: bool = Field(default=True)
    serbia_document_mirroring_enabled: bool = Field(default=True)
    serbia_ingestion_batch_size: int = Field(default=100)
    serbia_fetch_timeout_seconds: int = Field(default=30)
    serbia_fetch_max_retries: int = Field(default=2)
    serbia_refresh_mode: str = Field(default="pending_only")
    auto_seed_sources: bool = Field(default=False)
    recommendation_prompt_version: str = Field(default="recommendation_candidates.v1")
    explanation_prompt_version: str = Field(default="explanations.v1")
    project_review_prompt_version: str = Field(default="project_reviews.v1")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return settings."""
    return Settings()

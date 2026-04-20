from src.config.settings import Settings


def test_settings_default_auto_seed_sources_is_false() -> None:
    settings = Settings()

    assert settings.auto_seed_sources is False


def test_settings_allows_explicit_auto_seed_sources_opt_in() -> None:
    settings = Settings(auto_seed_sources=True)

    assert settings.auto_seed_sources is True


def test_settings_defaults_document_store_to_local() -> None:
    settings = Settings()

    assert settings.document_store_backend == "local"
    assert settings.admin_api_key == ""


def test_settings_accepts_gcp_document_store_configuration() -> None:
    settings = Settings(
        document_store_backend="gcs",
        gcp_project="ldt-project",
        gcs_bucket="ldt-documents",
        gcs_prefix="ldt/sources",
    )

    assert settings.document_store_backend == "gcs"
    assert settings.gcp_project == "ldt-project"
    assert settings.gcs_bucket == "ldt-documents"
    assert settings.gcs_prefix == "ldt/sources"


def test_settings_include_serbia_pipeline_controls() -> None:
    settings = Settings(
        serbia_dataset_loading_enabled=True,
        serbia_document_mirroring_enabled=True,
        serbia_ingestion_batch_size=25,
        serbia_fetch_timeout_seconds=45,
        serbia_fetch_max_retries=3,
        serbia_refresh_mode="force_refresh",
    )

    assert settings.serbia_dataset_loading_enabled is True
    assert settings.serbia_document_mirroring_enabled is True
    assert settings.serbia_ingestion_batch_size == 25
    assert settings.serbia_fetch_timeout_seconds == 45
    assert settings.serbia_fetch_max_retries == 3
    assert settings.serbia_refresh_mode == "force_refresh"

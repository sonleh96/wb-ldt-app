from src.config.settings import Settings


def test_settings_default_auto_seed_sources_is_false() -> None:
    settings = Settings()

    assert settings.auto_seed_sources is False


def test_settings_allows_explicit_auto_seed_sources_opt_in() -> None:
    settings = Settings(auto_seed_sources=True)

    assert settings.auto_seed_sources is True

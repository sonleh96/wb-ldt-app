"""Module for apps/worker/main.py."""

from src.config.settings import get_settings


def main() -> None:
    """Handle main."""
    settings = get_settings()
    print(f"Worker placeholder started for {settings.app_name} ({settings.environment})")


if __name__ == "__main__":
    main()

from functools import lru_cache
from app.settings import Settings, settings


@lru_cache()
def get_settings() -> Settings:
    """Dependency provider for cached application settings."""
    return settings

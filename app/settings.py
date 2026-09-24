from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Model & AI
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_API_KEYS: str = Field(
        default="",
        description="Comma-separated list of Google Gemini API keys"
    )
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Single Google Gemini API key"
    )

    # Provider Architecture (Cloud vs Local LLM)
    LLM_PROVIDER: str = Field(
        default="auto",
        description="LLM Provider to use: 'auto', 'gemini', or 'local'"
    )
    LOCAL_LLM_BASE_URL: str = Field(
        default="http://localhost:11434/v1",
        description="OpenAI-compatible base URL for local inference (Ollama, llama.cpp, vLLM, Kev)"
    )
    LOCAL_LLM_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model identifier for local inference (e.g. qwen2.5:3b, llama3.2:3b, kev)"
    )
    LOCAL_LLM_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="HTTP request timeout for local LLM inference in seconds"
    )

    # Concurrency
    MAX_CONCURRENT_PAGES_PER_PROJECT: int = 5
    MAX_WORKERS_PER_JOB: int = 4

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 0.5

    # In-memory Cache Fallback Limits
    MAX_CACHE_DOCUMENTS: int = 100
    MAX_CACHE_DOCUMENT_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_TOTAL_CACHE_BYTES: int = 256 * 1024 * 1024  # 256 MB

    # Engine Limits & Thresholds
    MAX_PAGES_PER_DOCUMENT: int = 20
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    GLOBAL_DEADLINE_SECONDS: float = 25.0
    OPENCV_BYPASS_WORD_THRESHOLD: int = 80
    CATALOGAR_IMAGENES_DEFAULT: bool = True

    # L2 Cache
    L2_CACHE_MIN_TOKENS: int = 32768
    L2_CACHE_TTL_MINUTES: int = 5

    @property
    def api_keys_list(self) -> List[str]:
        keys = []
        if self.GEMINI_API_KEYS:
            keys.extend([k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()])
        if self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip() not in keys:
            keys.append(self.GEMINI_API_KEY.strip())
        return keys


settings = Settings()

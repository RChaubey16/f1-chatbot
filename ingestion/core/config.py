"""Centralised settings loaded from .env via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://f1:f1secret@localhost:5432/f1kb"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    # HTTP
    user_agent: str = "F1Chatbot/0.1 (https://github.com/f1-chatbot; f1chatbot@example.com)"

    # Ingestion tuning
    request_delay_seconds: float = 0.5
    max_retries: int = 3
    chunk_size_structured: int = 512
    chunk_size_narrative: int = 800
    chunk_overlap: int = 80
    embedding_batch_size: int = 32


settings = Settings()

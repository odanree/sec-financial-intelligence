from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://portfolio_user:secret@localhost:5432/sec_financial_intelligence"

    # Azure AI Document Intelligence
    azure_doc_intelligence_endpoint: str = ""
    azure_doc_intelligence_key: str = ""

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # SEC EDGAR
    edgar_user_agent: str = "sec-financial-intelligence/1.0 contact@example.com"
    edgar_base_url: str = "https://data.sec.gov"
    edgar_rate_limit_delay: float = 0.12  # EDGAR rate limit: max 10 req/s

    # App
    mock_azure: bool = False  # True = skip Azure calls, return synthetic data
    app_env: str = "development"
    api_key: str = ""  # Bearer token; empty = auth disabled (dev mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()

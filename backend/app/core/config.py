from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Reads configuration from environment variables and an optional .env file.
    All fields have safe defaults so the app starts without a .env file,
    but production deployments must supply real values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://tp:tp@localhost:5432/transparentpolitics"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "tp_admin"
    minio_root_password: str = "tp_secret"
    minio_bucket_raw: str = "raw-ingest"

    # OpenSearch
    opensearch_url: str = "http://localhost:9200"

    # External API keys (empty string = not configured)
    congress_gov_api_key: str = ""
    openfec_api_key: str = ""


settings = Settings()

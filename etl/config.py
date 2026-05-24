"""
ETL-layer configuration.

Reads from environment variables and an optional .env file.
Checks both .env (project root, when running from TransparentPolitics/) and
../.env (one level up, when running dagster dev from the etl/ directory).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class EtlSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MinIO (S3-compatible object storage for raw ETL snapshots)
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "tp_admin"
    minio_root_password: str = "tp_secret"
    minio_bucket_raw: str = "raw-ingest"

    # External API keys (empty string = not configured)
    congress_gov_api_key: str = ""
    openfec_api_key: str = ""


settings = EtlSettings()

import os

from dagster import Definitions

from assets.congress.members import raw_congress_members
from assets.congress.upsert_members import congress_members
from resources import CongressGovResource, DatabaseResource, MinioSnapshotResource

defs = Definitions(
    assets=[raw_congress_members, congress_members],
    resources={
        "congress_gov": CongressGovResource(
            api_key=os.environ.get("CONGRESS_GOV_API_KEY", ""),
        ),
        "minio_snapshot": MinioSnapshotResource(
            endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.environ.get("MINIO_ROOT_USER", "tp_admin"),
            secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "tp_secret"),
            bucket=os.environ.get("MINIO_BUCKET_RAW", "raw-ingest"),
        ),
        "database": DatabaseResource(
            database_url=os.environ.get(
                "DATABASE_URL_SYNC",
                "postgresql://tp:tp@localhost:5432/transparentpolitics",
            ),
        ),
    },
    schedules=[],
    sensors=[],
)

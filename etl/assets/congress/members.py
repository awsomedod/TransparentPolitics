"""
Congress members ETL asset.

Pipeline: Congress.gov API + unitedstates/congress-legislators
       → MinIO snapshot → upsert DB

Data is stored as returned by the source. No vocabulary normalization is applied
upfront — if a specific transformation is needed to satisfy a DB constraint, it
will be added at that point with an explicit justification.
"""

import io
import json
import logging

from minio import Minio
from minio.error import S3Error

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MinIO snapshot
# ---------------------------------------------------------------------------

def _minio_client() -> Minio:
    """
    Build a MinIO client from ETL config.
    secure=False because local dev MinIO runs over plain HTTP on port 9000.
    """
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=False,
    )


def save_snapshot(client: Minio, object_name: str, data: list | dict) -> None:
    """
    Serialize data to JSON and write it to the raw-ingest MinIO bucket.

    object_name: the full object path inside the bucket, e.g.
        "congress/members/2026-05-23/member_list.json"
    data: any JSON-serialisable structure (list or dict).

    Creates the bucket automatically if it does not exist.
    Overwrites any existing object at the same path (idempotent — re-running
    the asset on the same day produces one file, not duplicates).
    Uses default=str so dates and UUIDs serialise without raising TypeError.
    """
    bucket = settings.minio_bucket_raw

    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("Created MinIO bucket '%s'", bucket)
    except S3Error as exc:
        logger.error("MinIO bucket check/create failed: %s", exc)
        raise

    payload = json.dumps(data, indent=2, default=str).encode("utf-8")

    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(payload),
        length=len(payload),
        content_type="application/json",
    )
    logger.info(
        "Snapshot saved: %s/%s (%d bytes)", bucket, object_name, len(payload)
    )

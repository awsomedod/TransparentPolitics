"""
MinIO raw-response snapshot helper.

Saves raw API responses as immutable JSON objects in MinIO before any
transformation or DB upsert. If a bug in downstream processing corrupts
data, the pipeline can replay DB writes from these snapshots without
re-hitting upstream APIs.

Object path convention:
    raw/{source}/{YYYY-MM-DD}/{filename}.json

Example:
    raw/congress-gov/2026-05-23/member_list_offset_0.json
    raw/congress-gov/2026-05-23/member_detail_M000355.json
    raw/unitedstates/2026-05-23/legislators_current.json
"""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, date, datetime
from typing import Any

from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class MinioSettings(BaseSettings):
    """Reads MinIO config from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "tp_admin"
    minio_root_password: str = "tp_secret"
    minio_bucket_raw: str = "raw-ingest"


class SnapshotMetadata(BaseModel):
    """Returned after a successful snapshot write."""

    bucket: str
    object_name: str
    size_bytes: int
    etag: str


class SnapshotStore:
    """
    Thin wrapper around the MinIO Python SDK providing snapshot
    save/retrieve/list operations scoped to a single bucket.

    The SDK is synchronous; this class is intentionally sync because
    MinIO writes are fast local-network operations and Dagster assets
    can run synchronously.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool = False,
    ) -> None:
        """
        All parameters are optional — defaults are read from environment
        variables via MinioSettings when not supplied explicitly.
        """
        settings = MinioSettings()
        self._bucket = bucket or settings.minio_bucket_raw
        self._client = Minio(
            endpoint=endpoint or settings.minio_endpoint,
            access_key=access_key or settings.minio_root_user,
            secret_key=secret_key or settings.minio_root_password,
            secure=secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Create the bucket if it does not exist yet."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Created MinIO bucket: %s", self._bucket)

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def client(self) -> Minio:
        return self._client

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        source: str,
        filename: str,
        data: Any,
        *,
        snapshot_date: date | None = None,
    ) -> SnapshotMetadata:
        """
        Serialize `data` to JSON and upload to MinIO.

        Args:
            source: Logical source name, e.g. "congress-gov" or "unitedstates".
            filename: Object filename (without path prefix), e.g. "member_list_offset_0.json".
                      A .json suffix is appended if not already present.
            data: Any JSON-serializable Python object (dict, list, etc.).
            snapshot_date: Date used in the path partition. Defaults to today (UTC).

        Returns:
            SnapshotMetadata with bucket, object_name, size_bytes, and etag.
        """
        if not filename.endswith(".json"):
            filename = f"{filename}.json"

        day = snapshot_date or datetime.now(UTC).date()
        object_name = f"raw/{source}/{day.isoformat()}/{filename}"

        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        stream = io.BytesIO(payload)
        size = len(payload)

        result = self._client.put_object(
            self._bucket,
            object_name,
            stream,
            length=size,
            content_type="application/json",
        )

        meta = SnapshotMetadata(
            bucket=self._bucket,
            object_name=object_name,
            size_bytes=size,
            etag=result.etag.strip('"'),
        )
        logger.debug("Saved snapshot: %s (%d bytes)", object_name, size)
        return meta

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_snapshot(self, object_name: str) -> Any:
        """
        Download and deserialize a JSON snapshot from MinIO.

        Args:
            object_name: Full object path, e.g. "raw/congress-gov/2026-05-23/members.json"

        Returns:
            The deserialized Python object (dict or list).

        Raises:
            S3Error: If the object does not exist or is not accessible.
        """
        response = self._client.get_object(self._bucket, object_name)
        try:
            return json.loads(response.read())
        finally:
            response.close()
            response.release_conn()

    # ------------------------------------------------------------------
    # List / query
    # ------------------------------------------------------------------

    def list_snapshots(
        self,
        source: str | None = None,
        snapshot_date: date | None = None,
    ) -> list[str]:
        """
        List snapshot object names, optionally filtered by source and/or date.

        Args:
            source: Filter to a specific source (e.g. "congress-gov").
            snapshot_date: Filter to a specific date partition.

        Returns:
            Sorted list of object name strings.
        """
        if source and snapshot_date:
            prefix = f"raw/{source}/{snapshot_date.isoformat()}/"
        elif source:
            prefix = f"raw/{source}/"
        else:
            prefix = "raw/"

        objects = self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
        return sorted(obj.object_name for obj in objects if not obj.is_dir)

    def snapshot_exists(self, object_name: str) -> bool:
        """Check whether a specific snapshot object exists."""
        try:
            self._client.stat_object(self._bucket, object_name)
            return True
        except S3Error:
            return False

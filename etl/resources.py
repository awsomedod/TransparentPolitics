"""
Dagster resources for the TransparentPolitics ETL.

Resources wrap external services (APIs, storage) so that assets can
declare dependencies on them and tests can substitute fakes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from dagster import ConfigurableResource
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from clients.congress_gov import CongressGovClient, MemberDetail, MemberSummary
from clients.minio_snapshot import SnapshotStore


class CongressGovResource(ConfigurableResource):
    """Dagster resource wrapping the Congress.gov async client."""

    api_key: str = ""

    def get_client(self) -> CongressGovClient:
        return CongressGovClient(api_key=self.api_key)

    def fetch_current_members(self) -> list[MemberSummary]:
        """Synchronous wrapper — fetches all current members."""
        async def _run() -> list[MemberSummary]:
            async with self.get_client() as client:
                return await client.get_current_members()
        return asyncio.run(_run())

    def fetch_member_detail(self, bioguide_id: str) -> MemberDetail:
        """Synchronous wrapper — fetches one member's full detail."""
        async def _run() -> MemberDetail:
            async with self.get_client() as client:
                return await client.get_member_detail(bioguide_id)
        return asyncio.run(_run())

    def fetch_member_details_batch(
        self, bioguide_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Fetch details for multiple members, returning raw dicts for snapshotting."""
        async def _run() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            async with self.get_client() as client:
                for bid in bioguide_ids:
                    detail = await client.get_member_detail(bid)
                    results.append(detail.model_dump())
            return results
        return asyncio.run(_run())


class MinioSnapshotResource(ConfigurableResource):
    """Dagster resource wrapping the MinIO SnapshotStore."""

    endpoint: str = "localhost:9000"
    access_key: str = "tp_admin"
    secret_key: str = "tp_secret"
    bucket: str = "raw-ingest"
    secure: bool = False

    def get_store(self) -> SnapshotStore:
        return SnapshotStore(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            bucket=self.bucket,
            secure=self.secure,
        )


class DatabaseResource(ConfigurableResource):
    """Dagster resource for synchronous PostgreSQL access via SQLAlchemy."""

    database_url: str = "postgresql://tp:tp@localhost:5432/transparentpolitics"

    def get_engine(self) -> Engine:
        return create_engine(self.database_url, echo=False)

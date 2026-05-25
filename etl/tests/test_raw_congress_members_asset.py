"""
Tests for the raw_congress_members Dagster asset.

Uses mocked Congress.gov responses (from fixtures) and a real MinIO instance
to verify the asset correctly fetches, snapshots, and returns metadata.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from dagster import materialize

from assets.congress.members import raw_congress_members
from clients.congress_gov import MemberDetail, MemberSummary
from clients.minio_snapshot import SnapshotStore
from resources import CongressGovResource, MinioSnapshotResource

FIXTURES = Path(__file__).parent / "fixtures"
_TEST_BUCKET = "test-asset-congress"


def _minio_available() -> bool:
    try:
        store = SnapshotStore(bucket=_TEST_BUCKET)
        return store.client.bucket_exists(store.bucket)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _minio_available(),
    reason="MinIO is not available at localhost:9000",
)


@pytest.fixture()
def minio_store() -> SnapshotStore:
    return SnapshotStore(bucket=_TEST_BUCKET)


@pytest.fixture(autouse=True)
def _cleanup(minio_store: SnapshotStore) -> None:
    yield
    objects = minio_store.client.list_objects(minio_store.bucket, recursive=True)
    for obj in objects:
        minio_store.client.remove_object(minio_store.bucket, obj.object_name)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _mock_members() -> list[MemberSummary]:
    """Build MemberSummary objects from the fixture file."""
    data = _load_fixture("congress_gov_member_list.json")
    return [MemberSummary.model_validate(m) for m in data["members"]]


def _mock_detail() -> MemberDetail:
    """Build a MemberDetail from the fixture file."""
    data = _load_fixture("congress_gov_member_detail.json")
    return MemberDetail.model_validate(data["member"])


class _FakeCongressGovResource(CongressGovResource):
    """Test double that returns fixture data instead of hitting the API."""

    def fetch_current_members(self) -> list[MemberSummary]:
        return _mock_members()

    def fetch_member_details_batch(self, bioguide_ids: list[str]) -> list[dict[str, Any]]:
        detail = _mock_detail()
        return [detail.model_dump()] * len(bioguide_ids)


class TestRawCongressMembersAsset:
    def test_materializes_and_snapshots(self, minio_store: SnapshotStore) -> None:
        """Asset fetches members, snapshots to MinIO, returns correct metadata."""
        result = materialize(
            [raw_congress_members],
            resources={
                "congress_gov": _FakeCongressGovResource(api_key="test-key"),
                "minio_snapshot": MinioSnapshotResource(bucket=_TEST_BUCKET),
            },
        )

        assert result.success

        # Verify snapshots were written to MinIO
        snapshots = minio_store.list_snapshots(source="congress-gov")
        assert len(snapshots) == 2
        assert any("member_list.json" in s for s in snapshots)
        assert any("member_details_all.json" in s for s in snapshots)

        # Verify list snapshot content
        list_snapshot = next(s for s in snapshots if "member_list" in s)
        list_data = minio_store.get_snapshot(list_snapshot)
        assert len(list_data) == len(_mock_members())

    def test_metadata_values(self, minio_store: SnapshotStore) -> None:
        """Asset returns expected metadata keys and values."""
        mock_members = _mock_members()

        result = materialize(
            [raw_congress_members],
            resources={
                "congress_gov": _FakeCongressGovResource(api_key="test-key"),
                "minio_snapshot": MinioSnapshotResource(bucket=_TEST_BUCKET),
            },
        )

        assert result.success
        event = result.get_asset_materialization_events()[0]
        metadata = event.step_materialization_data.materialization.metadata

        assert metadata["member_count"].value == len(mock_members)
        assert "congress-gov" in metadata["list_snapshot"].value
        assert "congress-gov" in metadata["details_snapshot"].value
        assert metadata["total_bytes"].value > 0

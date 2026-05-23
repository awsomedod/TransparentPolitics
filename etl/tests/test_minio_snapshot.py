"""
Tests for the MinIO snapshot helper.

Tests run against a real MinIO instance (docker-compose infra/docker-compose.yml).
If MinIO is unavailable, tests are skipped gracefully.
"""

import json
from datetime import UTC, date

import pytest

from clients.minio_snapshot import MinioSettings, SnapshotMetadata, SnapshotStore

# Use a dedicated test bucket to avoid polluting the dev bucket.
_TEST_BUCKET = "test-snapshot-helper"


def _minio_available() -> bool:
    """Return True if the local MinIO container is reachable."""
    try:
        store = SnapshotStore(bucket=_TEST_BUCKET)
        return store.client.bucket_exists(store.bucket)
    except Exception:
        return False


# Skip the entire module if MinIO is not running.
pytestmark = pytest.mark.skipif(
    not _minio_available(),
    reason="MinIO is not available at localhost:9000",
)


@pytest.fixture()
def store() -> SnapshotStore:
    """Provide a SnapshotStore connected to the test bucket."""
    return SnapshotStore(bucket=_TEST_BUCKET)


@pytest.fixture(autouse=True)
def _cleanup(store: SnapshotStore) -> None:
    """Remove all objects from the test bucket after each test."""
    yield
    objects = store.client.list_objects(store.bucket, recursive=True)
    for obj in objects:
        store.client.remove_object(store.bucket, obj.object_name)


# ──────────────────────────────────────────────────────────────────────────────
# save_snapshot
# ──────────────────────────────────────────────────────────────────────────────


class TestSaveSnapshot:
    def test_saves_dict_as_json(self, store: SnapshotStore) -> None:
        data = {"members": [{"bioguideId": "A000001", "name": "Adams, John"}]}
        meta = store.save_snapshot("congress-gov", "member_list.json", data)

        assert isinstance(meta, SnapshotMetadata)
        assert meta.bucket == _TEST_BUCKET
        assert "raw/congress-gov/" in meta.object_name
        assert meta.object_name.endswith("/member_list.json")
        assert meta.size_bytes > 0
        assert meta.etag != ""

    def test_saves_list_as_json(self, store: SnapshotStore) -> None:
        data = [{"id": {"bioguide": "S000033"}}, {"id": {"bioguide": "K000367"}}]
        meta = store.save_snapshot("unitedstates", "legislators_current.json", data)

        assert meta.object_name.startswith("raw/unitedstates/")
        assert meta.size_bytes == len(json.dumps(data, ensure_ascii=False, indent=2).encode())

    def test_appends_json_extension_if_missing(self, store: SnapshotStore) -> None:
        meta = store.save_snapshot("congress-gov", "detail_M000355", {"name": "McConnell"})
        assert meta.object_name.endswith("/detail_M000355.json")

    def test_respects_explicit_snapshot_date(self, store: SnapshotStore) -> None:
        explicit_date = date(2025, 1, 15)
        meta = store.save_snapshot(
            "congress-gov",
            "members.json",
            {"count": 536},
            snapshot_date=explicit_date,
        )
        assert "/2025-01-15/" in meta.object_name

    def test_uses_today_as_default_date(self, store: SnapshotStore) -> None:
        from datetime import datetime

        today = datetime.now(UTC).date().isoformat()
        meta = store.save_snapshot("congress-gov", "test.json", {})
        assert f"/{today}/" in meta.object_name

    def test_handles_unicode_content(self, store: SnapshotStore) -> None:
        data = {"name": "José García", "district": "Distrito Federal"}
        meta = store.save_snapshot("congress-gov", "unicode_test.json", data)
        retrieved = store.get_snapshot(meta.object_name)
        assert retrieved["name"] == "José García"


# ──────────────────────────────────────────────────────────────────────────────
# get_snapshot
# ──────────────────────────────────────────────────────────────────────────────


class TestGetSnapshot:
    def test_round_trip_dict(self, store: SnapshotStore) -> None:
        original = {"status": "ok", "pagination": {"count": 536, "offset": 0}}
        meta = store.save_snapshot("congress-gov", "health.json", original)

        retrieved = store.get_snapshot(meta.object_name)
        assert retrieved == original

    def test_round_trip_list(self, store: SnapshotStore) -> None:
        original = [{"bioguide": "A000001"}, {"bioguide": "B000002"}]
        meta = store.save_snapshot("test-source", "list.json", original)

        retrieved = store.get_snapshot(meta.object_name)
        assert retrieved == original

    def test_raises_on_missing_object(self, store: SnapshotStore) -> None:
        from minio.error import S3Error

        with pytest.raises(S3Error):
            store.get_snapshot("raw/nonexistent/2025-01-01/missing.json")


# ──────────────────────────────────────────────────────────────────────────────
# list_snapshots
# ──────────────────────────────────────────────────────────────────────────────


class TestListSnapshots:
    def test_list_all(self, store: SnapshotStore) -> None:
        store.save_snapshot("src-a", "file1.json", {}, snapshot_date=date(2025, 3, 1))
        store.save_snapshot("src-b", "file2.json", {}, snapshot_date=date(2025, 3, 2))

        names = store.list_snapshots()
        assert len(names) == 2

    def test_filter_by_source(self, store: SnapshotStore) -> None:
        store.save_snapshot("congress-gov", "a.json", {}, snapshot_date=date(2025, 3, 1))
        store.save_snapshot("unitedstates", "b.json", {}, snapshot_date=date(2025, 3, 1))

        names = store.list_snapshots(source="congress-gov")
        assert len(names) == 1
        assert "congress-gov" in names[0]

    def test_filter_by_source_and_date(self, store: SnapshotStore) -> None:
        store.save_snapshot("congress-gov", "day1.json", {}, snapshot_date=date(2025, 3, 1))
        store.save_snapshot("congress-gov", "day2.json", {}, snapshot_date=date(2025, 3, 2))

        names = store.list_snapshots(source="congress-gov", snapshot_date=date(2025, 3, 1))
        assert len(names) == 1
        assert "day1.json" in names[0]

    def test_returns_sorted(self, store: SnapshotStore) -> None:
        store.save_snapshot("src", "z.json", {}, snapshot_date=date(2025, 1, 1))
        store.save_snapshot("src", "a.json", {}, snapshot_date=date(2025, 1, 1))

        names = store.list_snapshots(source="src")
        assert names == sorted(names)


# ──────────────────────────────────────────────────────────────────────────────
# snapshot_exists
# ──────────────────────────────────────────────────────────────────────────────


class TestSnapshotExists:
    def test_returns_true_for_existing(self, store: SnapshotStore) -> None:
        meta = store.save_snapshot("congress-gov", "exists.json", {"x": 1})
        assert store.snapshot_exists(meta.object_name) is True

    def test_returns_false_for_missing(self, store: SnapshotStore) -> None:
        assert store.snapshot_exists("raw/nope/2025-01-01/nope.json") is False


# ──────────────────────────────────────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────────────────────────────────────


class TestMinioSettings:
    def test_defaults(self) -> None:
        s = MinioSettings()
        assert s.minio_endpoint == "localhost:9000"
        assert s.minio_bucket_raw == "raw-ingest"
        assert s.minio_root_user == "tp_admin"
        assert s.minio_root_password == "tp_secret"

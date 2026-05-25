"""
Congress members raw fetch asset.

Fetches all current Congress members from the Congress.gov API and
snapshots raw responses to MinIO for downstream processing.
"""

from datetime import UTC, datetime
from typing import Any

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from resources import CongressGovResource, MinioSnapshotResource


@asset(
    group_name="congress",
    description=(
        "Fetch all current Congress members (list + full details) from "
        "Congress.gov API and snapshot raw responses to MinIO."
    ),
)
def raw_congress_members(
    context: AssetExecutionContext,
    congress_gov: CongressGovResource,
    minio_snapshot: MinioSnapshotResource,
) -> MaterializeResult:
    """
    Fetches current members from Congress.gov, saves raw responses to MinIO.

    Steps:
      1. GET /member?currentMember=true (paginated) → snapshot member list
      2. For each member, GET /member/{bioguideId} → snapshot detail
      3. Return metadata about what was stored
    """
    store = minio_snapshot.get_store()
    today = datetime.now(UTC).date()

    context.log.info("Fetching current member list from Congress.gov...")
    members = congress_gov.fetch_current_members()
    context.log.info("Fetched %d members", len(members))

    list_data = [m.model_dump() for m in members]
    list_meta = store.save_snapshot(
        source="congress-gov",
        filename="member_list.json",
        data=list_data,
        snapshot_date=today,
    )
    context.log.info("Snapshot saved: %s (%d bytes)", list_meta.object_name, list_meta.size_bytes)

    bioguide_ids = [m.bioguide_id for m in members]
    context.log.info("Fetching details for %d members...", len(bioguide_ids))

    details: list[dict[str, Any]] = congress_gov.fetch_member_details_batch(bioguide_ids)

    details_meta = store.save_snapshot(
        source="congress-gov",
        filename="member_details_all.json",
        data=details,
        snapshot_date=today,
    )
    context.log.info(
        "Details snapshot saved: %s (%d bytes)",
        details_meta.object_name,
        details_meta.size_bytes,
    )

    return MaterializeResult(
        metadata={
            "member_count": MetadataValue.int(len(members)),
            "list_snapshot": MetadataValue.text(list_meta.object_name),
            "details_snapshot": MetadataValue.text(details_meta.object_name),
            "snapshot_date": MetadataValue.text(today.isoformat()),
            "total_bytes": MetadataValue.int(
                list_meta.size_bytes + details_meta.size_bytes
            ),
        },
    )

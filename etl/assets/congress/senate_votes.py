"""
Senate votes snapshot asset.

Fetches all Senate roll call votes for the 119th Congress from senate.gov
XML and saves raw responses to MinIO. Saves two snapshots per session:
  - senate_votes_list_s{N}.json — vote menu summary (for discovery)
  - senate_votes_detail_s{N}.json — full vote detail + members for every vote
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from clients.senate_votes import SenateVotesClient
from resources import MinioSnapshotResource


def _fetch_session(congress: int, session: int) -> dict[str, Any]:
    """Synchronous wrapper: fetch vote list + all individual vote details."""

    async def _run() -> dict[str, Any]:
        async with SenateVotesClient() as client:
            vote_list = await client.get_session_votes(congress, session)

            vote_numbers = [v["vote_number"] for v in vote_list]
            details: list[dict[str, Any]] = []
            for vn in vote_numbers:
                detail = await client.get_vote(congress, session, vn)
                details.append(detail)

            return {"vote_list": vote_list, "details": details}

    return asyncio.run(_run())


@asset(
    group_name="congress",
    description=(
        "Fetch all Senate roll call votes for the 119th Congress "
        "and snapshot raw responses to MinIO."
    ),
)
def raw_senate_votes(
    context: AssetExecutionContext,
    minio_snapshot: MinioSnapshotResource,
) -> MaterializeResult:
    """
    Fetches Senate votes for both sessions of the 119th Congress,
    snapshots raw data to MinIO.
    """
    store = minio_snapshot.get_store()
    today = datetime.now(UTC).date()

    congress = 119
    total_votes = 0
    total_member_rows = 0
    snapshots_saved: list[str] = []

    for session in (1, 2):
        context.log.info(
            "Fetching Senate votes: %dth Congress, session %d...",
            congress, session,
        )

        try:
            data = _fetch_session(congress, session)
        except Exception as e:
            context.log.warning("Session %d fetch failed: %s", session, e)
            continue

        vote_list = data["vote_list"]
        details = data["details"]

        if not vote_list:
            context.log.info("No votes found for session %d, skipping.", session)
            continue

        total_votes += len(details)
        total_member_rows += sum(len(d.get("members", [])) for d in details)

        list_meta = store.save_snapshot(
            source="senate-gov",
            filename=f"senate_votes_list_s{session}.json",
            data=vote_list,
            snapshot_date=today,
        )
        context.log.info(
            "Saved vote list: %s (%d votes, %d bytes)",
            list_meta.object_name, len(vote_list), list_meta.size_bytes,
        )
        snapshots_saved.append(list_meta.object_name)

        details_meta = store.save_snapshot(
            source="senate-gov",
            filename=f"senate_votes_detail_s{session}.json",
            data=details,
            snapshot_date=today,
        )
        context.log.info(
            "Saved vote details: %s (%d votes, %d bytes)",
            details_meta.object_name, len(details), details_meta.size_bytes,
        )
        snapshots_saved.append(details_meta.object_name)

    return MaterializeResult(
        metadata={
            "congress": MetadataValue.int(congress),
            "total_votes": MetadataValue.int(total_votes),
            "total_member_vote_rows": MetadataValue.int(total_member_rows),
            "snapshots": MetadataValue.text(", ".join(snapshots_saved)),
        },
    )

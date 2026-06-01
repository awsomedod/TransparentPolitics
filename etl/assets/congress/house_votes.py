"""
House votes snapshot asset.

Fetches all House roll call votes for the 119th Congress from Congress.gov
and saves raw responses to MinIO. Saves two snapshots per session:
  - house_votes_list_{session}.json — vote summary list
  - house_votes_members_{session}.json — per-member positions for all votes
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from clients.house_votes import HouseVotesClient
from resources import MinioSnapshotResource


def _fetch_session(api_key: str, congress: int, session: int) -> dict[str, Any]:
    """Synchronous wrapper: fetch vote list + all member positions for a session."""

    async def _run() -> dict[str, Any]:
        async with HouseVotesClient(api_key=api_key) as client:
            votes = await client.get_session_votes(congress, session)

            all_member_votes: list[dict[str, Any]] = []
            for vote in votes:
                vote_num = vote["rollCallNumber"]
                members = await client.get_vote_members(congress, session, vote_num)
                all_member_votes.append({
                    "rollCallNumber": vote_num,
                    "congress": congress,
                    "session": session,
                    "members": members,
                })

            return {"votes": votes, "member_votes": all_member_votes}

    return asyncio.run(_run())


@asset(
    group_name="congress",
    description=(
        "Fetch all House roll call votes for the 119th Congress "
        "and snapshot raw responses to MinIO."
    ),
)
def raw_house_votes(
    context: AssetExecutionContext,
    minio_snapshot: MinioSnapshotResource,
) -> MaterializeResult:
    """
    Fetches House votes for both sessions of the 119th Congress,
    snapshots raw data to MinIO.
    """
    store = minio_snapshot.get_store()
    today = datetime.now(UTC).date()

    import os
    api_key = os.environ.get("CONGRESS_GOV_API_KEY", "")
    if not api_key:
        raise RuntimeError("CONGRESS_GOV_API_KEY is not set")

    congress = 119
    total_votes = 0
    total_member_rows = 0
    snapshots_saved: list[str] = []

    for session in (1, 2):
        context.log.info("Fetching House votes: %dth Congress, session %d...", congress, session)

        try:
            data = _fetch_session(api_key, congress, session)
        except Exception as e:
            context.log.warning("Session %d fetch failed: %s", session, e)
            continue

        votes = data["votes"]
        member_votes = data["member_votes"]

        if not votes:
            context.log.info("No votes found for session %d, skipping.", session)
            continue

        total_votes += len(votes)
        total_member_rows += sum(len(mv["members"]) for mv in member_votes)

        list_meta = store.save_snapshot(
            source="congress-gov",
            filename=f"house_votes_list_s{session}.json",
            data=votes,
            snapshot_date=today,
        )
        context.log.info(
            "Saved vote list: %s (%d votes, %d bytes)",
            list_meta.object_name, len(votes), list_meta.size_bytes,
        )
        snapshots_saved.append(list_meta.object_name)

        members_meta = store.save_snapshot(
            source="congress-gov",
            filename=f"house_votes_members_s{session}.json",
            data=member_votes,
            snapshot_date=today,
        )
        context.log.info(
            "Saved member votes: %s (%d bytes)",
            members_meta.object_name, members_meta.size_bytes,
        )
        snapshots_saved.append(members_meta.object_name)

    return MaterializeResult(
        metadata={
            "congress": MetadataValue.int(congress),
            "total_votes": MetadataValue.int(total_votes),
            "total_member_vote_rows": MetadataValue.int(total_member_rows),
            "snapshots": MetadataValue.text(", ".join(snapshots_saved)),
        },
    )

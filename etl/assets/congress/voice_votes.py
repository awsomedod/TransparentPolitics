"""
Voice vote snapshot asset.

Scans all bills in the 119th Congress to find those that passed by
voice vote, without objection, or unanimous consent. Saves a snapshot
of these non-roll-call votes with their metadata.

Voice votes have no per-member positions (that's why they're voice votes),
but we capture what was voted on, the result, and the date.

Limitation: only captures voice votes that are the bill's latest action.
A bill that passed the House by voice vote but was later amended in the
Senate by roll call would not be captured here.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from resources import MinioSnapshotResource

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.congress.gov/v3"
_VOICE_MARKERS = ["voice vote", "without objection", "unanimous consent"]
_MIN_INTERVAL = 3600.0 / 4_000


def _classify_passage(action_text: str) -> str:
    """Extract the passage type from the action text."""
    text = action_text.lower()
    if "voice vote" in text:
        return "voice vote"
    if "without objection" in text:
        return "without objection"
    if "unanimous consent" in text:
        return "unanimous consent"
    return "unknown"


def _extract_result(action_text: str) -> str:
    """Extract the result (Agreed to, Passed, etc.) from action text."""
    text = action_text.lower()
    if "passed" in text:
        return "Passed"
    if "agreed to" in text:
        return "Agreed to"
    if "adopted" in text:
        return "Adopted"
    if "confirmed" in text:
        return "Confirmed"
    return "Passed"


async def _scan_voice_votes(api_key: str, congress: int) -> list[dict[str, Any]]:
    """Paginate through all bills and find those with voice vote actions."""
    voice_bills: list[dict[str, Any]] = []
    offset = 0
    limit = 250
    last_request_at = 0.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - last_request_at
            gap = _MIN_INTERVAL - elapsed
            if gap > 0:
                await asyncio.sleep(gap)

            for attempt in range(3):
                last_request_at = loop.time()
                try:
                    resp = await client.get(
                        f"{_BASE_URL}/bill/{congress}",
                        params={
                            "api_key": api_key,
                            "format": "json",
                            "limit": limit,
                            "offset": offset,
                        },
                    )
                    if resp.status_code == 429:
                        backoff = 10 * (2 ** attempt)
                        logger.warning(
                            "Rate-limited — sleeping %ss (attempt %s/3)",
                            backoff, attempt + 1,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    break
                except httpx.HTTPStatusError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed after 3 retries at offset {offset}")

            data = resp.json()
            total = data.get("pagination", {}).get("count", 0)

            for b in data.get("bills", []):
                latest = b.get("latestAction")
                if latest is None:
                    continue
                action_text = (latest.get("text") or "")
                if any(marker in action_text.lower() for marker in _VOICE_MARKERS):
                    voice_bills.append({
                        "type": b.get("type", ""),
                        "number": b.get("number", ""),
                        "title": b.get("title", ""),
                        "origin_chamber": b.get("originChamber", ""),
                        "latest_action_text": action_text,
                        "latest_action_date": latest.get("actionDate", ""),
                        "passage_type": _classify_passage(action_text),
                        "result": _extract_result(action_text),
                        "congress": congress,
                        "url": b.get("url", ""),
                    })

            offset += limit
            if offset >= total:
                break

    return voice_bills


@asset(
    group_name="congress",
    description=(
        "Scan all 119th Congress bills for voice votes, unanimous consent, "
        "and without-objection passages. Snapshot to MinIO."
    ),
)
def raw_voice_votes(
    context: AssetExecutionContext,
    minio_snapshot: MinioSnapshotResource,
) -> MaterializeResult:
    """
    Scans all bills in the 119th Congress, filters for voice vote passages,
    saves to MinIO.
    """
    store = minio_snapshot.get_store()
    today = datetime.now(UTC).date()

    api_key = os.environ.get("CONGRESS_GOV_API_KEY", "")
    if not api_key:
        raise RuntimeError("CONGRESS_GOV_API_KEY is not set")

    context.log.info("Scanning 119th Congress bills for voice votes...")
    voice_bills = asyncio.run(_scan_voice_votes(api_key, 119))
    context.log.info("Found %d voice vote bills", len(voice_bills))

    meta = store.save_snapshot(
        source="congress-gov",
        filename="voice_votes.json",
        data=voice_bills,
        snapshot_date=today,
    )
    context.log.info(
        "Saved: %s (%d bytes)", meta.object_name, meta.size_bytes,
    )

    return MaterializeResult(
        metadata={
            "voice_vote_count": MetadataValue.int(len(voice_bills)),
            "snapshot": MetadataValue.text(meta.object_name),
        },
    )

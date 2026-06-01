"""
Vote-referenced data snapshot asset.

Reads House and Senate vote snapshots from MinIO, extracts all referenced
bills, nominations, and amendments, then fetches their metadata from the
Congress.gov API and saves to MinIO.

Produces three snapshot files:
  - legislation_details.json — bill/resolution metadata
  - nomination_details.json — nomination metadata
  - amendment_details.json — amendment metadata
"""

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from clients.congress_data import BILL_TYPE_MAP, CongressDataClient
from resources import MinioSnapshotResource

logger = logging.getLogger(__name__)


def _extract_references(store: Any) -> tuple[
    set[tuple[str, str]], set[str], set[tuple[str, str]]
]:
    """
    Scan vote snapshots and extract unique bills, nominations, and amendments.
    Returns (bills, nominations, amendments) where:
      bills = {(api_type, number), ...}
      nominations = {number, ...}
      amendments = {(api_type, number), ...}
    """
    bills: set[tuple[str, str]] = set()
    nominations: set[str] = set()
    amendments: set[tuple[str, str]] = set()

    # Find latest House vote snapshots
    house_snapshots = store.list_snapshots(source="congress-gov")
    for session in (1, 2):
        fname = f"house_votes_list_s{session}.json"
        matching = [s for s in house_snapshots if fname in s]
        if not matching:
            continue
        try:
            votes = store.get_snapshot(matching[-1])
        except Exception:
            continue
        for v in votes:
            leg_type = (v.get("legislationType") or "").strip().lower()
            leg_num = (v.get("legislationNumber") or "").strip()
            if leg_type and leg_num:
                api_type = BILL_TYPE_MAP.get(leg_type)
                if api_type:
                    bills.add((api_type, leg_num))

    # Find latest Senate vote snapshots
    senate_snapshots = store.list_snapshots(source="senate-gov")
    for session in (1, 2):
        fname = f"senate_votes_detail_s{session}.json"
        matching = [s for s in senate_snapshots if fname in s]
        if not matching:
            continue
        try:
            details = store.get_snapshot(matching[-1])
        except Exception:
            continue
        for d in details:
            doc = d.get("document", {})
            doc_type = (doc.get("type") or "").strip()
            doc_num = (doc.get("number") or "").strip()
            if doc_type and doc_num:
                if doc_type == "PN":
                    nominations.add(doc_num)
                else:
                    api_type = BILL_TYPE_MAP.get(doc_type.lower().rstrip("."))
                    if api_type:
                        bills.add((api_type, doc_num))

            amend = d.get("amendment", {})
            amend_str = (amend.get("number") or "").strip()
            if amend_str:
                match = re.match(r"(S\.Amdt\.|H\.Amdt\.)\s*(\d+)", amend_str)
                if match:
                    prefix = match.group(1)
                    num = match.group(2)
                    amend_type = "samdt" if prefix.startswith("S") else "hamdt"
                    amendments.add((amend_type, num))

    return bills, nominations, amendments


def _fetch_all(
    api_key: str,
    congress: int,
    bills: set[tuple[str, str]],
    nominations: set[str],
    amendments: set[tuple[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    """Fetch all referenced items from Congress.gov API."""

    async def _run() -> dict[str, list[dict[str, Any]]]:
        async with CongressDataClient(api_key=api_key) as client:
            bill_results: list[dict[str, Any]] = []
            for bill_type, bill_num in sorted(bills):
                try:
                    bill = await client.get_bill(congress, bill_type, bill_num)
                    bill_results.append(bill)
                except Exception as e:
                    logger.warning("Failed to fetch bill %s/%s: %s", bill_type, bill_num, e)

            nom_results: list[dict[str, Any]] = []
            for nom_num in sorted(nominations):
                try:
                    nom = await client.get_nomination(congress, nom_num)
                    nom_results.append(nom)
                except Exception as e:
                    logger.warning("Failed to fetch nomination %s: %s", nom_num, e)

            amend_results: list[dict[str, Any]] = []
            for amend_type, amend_num in sorted(amendments):
                try:
                    amend = await client.get_amendment(
                        congress, amend_type, amend_num
                    )
                    amend_results.append(amend)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch amendment %s/%s: %s",
                        amend_type, amend_num, e,
                    )

            return {
                "bills": bill_results,
                "nominations": nom_results,
                "amendments": amend_results,
            }

    return asyncio.run(_run())


@asset(
    group_name="congress",
    deps=["raw_house_votes", "raw_senate_votes"],
    description=(
        "Fetch metadata for all bills, nominations, and amendments "
        "referenced in vote snapshots."
    ),
)
def raw_vote_references(
    context: AssetExecutionContext,
    minio_snapshot: MinioSnapshotResource,
) -> MaterializeResult:
    """
    Scans vote snapshots for bill/nomination/amendment references,
    fetches their metadata from Congress.gov, saves to MinIO.
    """
    store = minio_snapshot.get_store()
    today = datetime.now(UTC).date()

    api_key = os.environ.get("CONGRESS_GOV_API_KEY", "")
    if not api_key:
        raise RuntimeError("CONGRESS_GOV_API_KEY is not set")

    bills, nominations, amendments = _extract_references(store)
    context.log.info(
        "Found references: %d bills, %d nominations, %d amendments",
        len(bills), len(nominations), len(amendments),
    )

    results = _fetch_all(api_key, 119, bills, nominations, amendments)
    snapshots_saved: list[str] = []

    if results["bills"]:
        meta = store.save_snapshot(
            source="congress-gov",
            filename="legislation_details.json",
            data=results["bills"],
            snapshot_date=today,
        )
        context.log.info(
            "Saved %d bills: %s (%d bytes)",
            len(results["bills"]), meta.object_name, meta.size_bytes,
        )
        snapshots_saved.append(meta.object_name)

    if results["nominations"]:
        meta = store.save_snapshot(
            source="congress-gov",
            filename="nomination_details.json",
            data=results["nominations"],
            snapshot_date=today,
        )
        context.log.info(
            "Saved %d nominations: %s (%d bytes)",
            len(results["nominations"]), meta.object_name, meta.size_bytes,
        )
        snapshots_saved.append(meta.object_name)

    if results["amendments"]:
        meta = store.save_snapshot(
            source="congress-gov",
            filename="amendment_details.json",
            data=results["amendments"],
            snapshot_date=today,
        )
        context.log.info(
            "Saved %d amendments: %s (%d bytes)",
            len(results["amendments"]), meta.object_name, meta.size_bytes,
        )
        snapshots_saved.append(meta.object_name)

    return MaterializeResult(
        metadata={
            "bills_fetched": MetadataValue.int(len(results["bills"])),
            "nominations_fetched": MetadataValue.int(len(results["nominations"])),
            "amendments_fetched": MetadataValue.int(len(results["amendments"])),
            "snapshots": MetadataValue.text(", ".join(snapshots_saved)),
        },
    )

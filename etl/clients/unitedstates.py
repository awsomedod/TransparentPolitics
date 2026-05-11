"""
unitedstates/congress-legislators bulk data client.

Provides the canonical cross-ID mapping for all current federal legislators.
This is a single static JSON file download — no auth, no rate limit.

Source:  https://github.com/unitedstates/congress-legislators
License: Public domain (Unlicense)
Attribution: "Member ID data from unitedstates/congress-legislators"

Why this source: Congress.gov API does not return all cross-source IDs in a
single call. This file maps bioguide_id to FEC IDs, ICPSR, OpenSecrets,
VoteSmart, Ballotpedia, Wikipedia, and Wikidata in one place. It is updated
by maintainers within hours of changes and is the industry-standard ID backbone
used by GovTrack, FiveThirtyEight, and ProPublica.
"""

import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_CURRENT_URL = (
    "https://unitedstates.io/congress-legislators/legislators-current.json"
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LegislatorIds(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bioguide: str
    # All fields below are optional — not every member has every ID.
    thomas: str | None = None
    # FEC IDs are an array: a candidate may have separate IDs per election cycle.
    fec: list[str] = Field(default_factory=list)
    icpsr: int | None = None
    opensecrets: str | None = None
    votesmart: int | None = None
    ballotpedia: str | None = None
    wikipedia: str | None = None
    wikidata: str | None = None
    google_entity_id: str | None = None


class LegislatorRecord(BaseModel):
    """
    One row from legislators-current.json.
    Only the 'id' block is used — all other fields (bio, name, terms, social)
    are intentionally excluded because Congress.gov is the primary source for
    that data. We only use this file for ID cross-referencing.
    """
    model_config = ConfigDict(populate_by_name=True)

    id: LegislatorIds


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class UnitedStatesClient:
    """
    Downloads legislators-current.json from unitedstates.io.
    No auth, no rate limit — one HTTP GET per run.

    Usage:

        client = UnitedStatesClient()
        records = await client.get_current_legislators()
        # Each record.id.bioguide is the join key to Congress.gov data.
    """

    def __init__(self, url: str = _CURRENT_URL) -> None:
        """url: override for testing against a local fixture."""
        self._url = url

    async def get_current_legislators(self) -> list[LegislatorRecord]:
        """
        Download and parse legislators-current.json.
        Returns one LegislatorRecord per current member.
        Raises httpx.HTTPStatusError if the download fails.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(self._url)
            resp.raise_for_status()
            raw: list[dict] = resp.json()

        records = [LegislatorRecord.model_validate(row) for row in raw]
        logger.info(
            "unitedstates/congress-legislators: loaded %d current legislator ID records",
            len(records),
        )
        return records

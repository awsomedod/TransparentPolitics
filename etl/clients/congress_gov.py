"""
Congress.gov API v3 client.

Primary source for federal member biographical data, current terms,
party affiliation, and cross-source IDs.

Docs:     https://api.congress.gov/
Sign-up:  https://api.congress.gov/sign-up/
Rate limit: 5,000 requests / hour (we cap at 4,000 to stay safe).
"""

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.congress.gov/v3"
_DEFAULT_CAP = 4_000  # requests/hour — conservative margin below the 5,000 limit


# ---------------------------------------------------------------------------
# Response models
# Only fields we actually use are declared; extra fields are silently ignored.
# ---------------------------------------------------------------------------

class _AliasModel(BaseModel):
    """Base that allows both the Python field name and its camelCase alias."""
    model_config = ConfigDict(populate_by_name=True)


class MemberSummary(_AliasModel):
    """One item from GET /v3/member (list endpoint)."""

    bioguide_id: str = Field(alias="bioguideId")
    name: str                                         # "Last, First" format
    party_name: str | None = Field(None, alias="partyName")
    state: str | None = None                          # 2-letter code
    district: int | None = None                       # House only; None for Senate


class _Pagination(_AliasModel):
    count: int = 0


class _MemberListResponse(_AliasModel):
    members: list[MemberSummary] = Field(default_factory=list)
    pagination: _Pagination = Field(default_factory=_Pagination)


class TermItem(_AliasModel):
    chamber: str | None = None                        # "Senate" | "House of Representatives"
    member_type: str | None = Field(None, alias="memberType")  # "Senator" | "Representative" | …
    congress: int | None = None
    start_year: int | None = Field(None, alias="startYear")
    end_year: int | None = Field(None, alias="endYear")
    state_code: str | None = Field(None, alias="stateCode")
    state_name: str | None = Field(None, alias="stateName")


class PartyHistoryItem(_AliasModel):
    party_name: str | None = Field(None, alias="partyName")
    party_abbreviation: str | None = Field(None, alias="partyAbbreviation")
    start_year: int | None = Field(None, alias="startYear")


class MemberDetail(_AliasModel):
    """Full record from GET /v3/member/{bioguideId}."""

    bioguide_id: str = Field(alias="bioguideId")
    # Congress.gov may return either or both name formats.
    direct_order_name: str | None = Field(None, alias="directOrderName")   # "First Last"
    inverted_order_name: str | None = Field(None, alias="invertedOrderName")  # "Last, First"
    birth_year: int | None = Field(None, alias="birthYear")
    death_year: int | None = Field(None, alias="deathYear")
    official_website_url: str | None = Field(None, alias="officialWebsiteUrl")
    state: str | None = None
    district: int | None = None
    party_history: list[PartyHistoryItem] = Field(default_factory=list, alias="partyHistory")
    terms: list[TermItem] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Best available human-readable name."""
        return self.direct_order_name or self.inverted_order_name or self.bioguide_id

    @property
    def canonical_name(self) -> str:
        """Inverted (Last, First) form used for sorting and dedup."""
        return self.inverted_order_name or self.direct_order_name or self.bioguide_id

    @property
    def current_party_name(self) -> str | None:
        """Most recent party name from partyHistory (highest startYear wins)."""
        if not self.party_history:
            return None
        return max(self.party_history, key=lambda p: p.start_year or 0).party_name

    @property
    def current_term(self) -> TermItem | None:
        """Most recent term (highest startYear wins)."""
        if not self.terms:
            return None
        return max(self.terms, key=lambda t: t.start_year or 0)


class _MemberDetailResponse(_AliasModel):
    member: MemberDetail


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CongressGovClient:
    """
    Async httpx client for Congress.gov API v3.

    Usage (async context manager):

        async with CongressGovClient(api_key="...") as client:
            members = await client.get_current_members()
            detail  = await client.get_member_detail("A000360")
    """

    def __init__(self, api_key: str, *, requests_per_hour: int = _DEFAULT_CAP) -> None:
        """
        api_key: key from https://api.congress.gov/sign-up/
        requests_per_hour: self-imposed cap (default 4,000 < API limit of 5,000).
        """
        self._api_key = api_key
        self._min_interval: float = 3600.0 / requests_per_hour
        self._last_request_at: float = 0.0
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "CongressGovClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retries: int = 3,
    ) -> Any:
        """
        Rate-limited GET with exponential backoff on HTTP 429.
        Returns the parsed JSON body.
        """
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_request_at
        gap = self._min_interval - elapsed
        if gap > 0:
            await asyncio.sleep(gap)

        merged_params = {"api_key": self._api_key, **(params or {})}

        for attempt in range(retries):
            self._last_request_at = loop.time()
            try:
                resp = await self._http.get(path, params=merged_params)

                if resp.status_code == 429:
                    backoff = 10 * (2 ** attempt)  # 10 s, 20 s, 40 s
                    logger.warning(
                        "Congress.gov rate-limited on %s — sleeping %s s (attempt %s/%s)",
                        path, backoff, attempt + 1, retries,
                    )
                    await asyncio.sleep(backoff)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as exc:
                if attempt == retries - 1:
                    raise
                logger.warning(
                    "Congress.gov HTTP %s on %s — retry %s/%s",
                    exc.response.status_code, path, attempt + 1, retries,
                )
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"Congress.gov request failed after {retries} retries: {path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_current_members(self) -> list[MemberSummary]:
        """
        Return every current member of Congress.
        Paginates automatically (API max 250 per page).
        """
        members: list[MemberSummary] = []
        offset, limit = 0, 250

        while True:
            data = await self._get(
                "/member",
                {"currentMember": "true", "limit": limit, "offset": offset},
            )
            page = _MemberListResponse.model_validate(data)
            members.extend(page.members)

            if offset + limit >= page.pagination.count:
                break
            offset += limit

        logger.info("Congress.gov: fetched %d current members", len(members))
        return members

    async def get_member_detail(self, bioguide_id: str) -> MemberDetail:
        """Return full biographical and term detail for one member."""
        data = await self._get(f"/member/{bioguide_id}")
        return _MemberDetailResponse.model_validate(data).member

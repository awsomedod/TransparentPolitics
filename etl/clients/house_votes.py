"""
Congress.gov House Roll Call Votes client.

Fetches House roll call vote data from the Congress.gov API v3.

Endpoints used:
    GET /v3/house-vote/{congress}/{session}          — list all votes in a session
    GET /v3/house-vote/{congress}/{session}/{number} — single vote detail
    GET /v3/house-vote/{congress}/{session}/{number}/members — per-member positions

Docs: https://api.congress.gov/
Rate limit: 5,000 req/hr (client self-caps at 4,000)
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.congress.gov/v3"
_DEFAULT_CAP = 4_000


class HouseVotesClient:
    """
    Async client for Congress.gov House Roll Call Votes endpoints.

    Usage:
        async with HouseVotesClient(api_key="...") as client:
            votes = await client.get_session_votes(119, 1)
            detail = await client.get_vote_detail(119, 1, 240)
            members = await client.get_vote_members(119, 1, 240)
    """

    def __init__(self, api_key: str, *, requests_per_hour: int = _DEFAULT_CAP) -> None:
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

    async def __aenter__(self) -> "HouseVotesClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _get(
        self, path: str, params: dict[str, Any] | None = None, *, retries: int = 3
    ) -> Any:
        """Rate-limited GET with retry on 429 and transient server errors."""
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_request_at
        gap = self._min_interval - elapsed
        if gap > 0:
            await asyncio.sleep(gap)

        merged_params = {"api_key": self._api_key, "format": "json", **(params or {})}

        for attempt in range(retries):
            self._last_request_at = loop.time()
            try:
                resp = await self._http.get(path, params=merged_params)

                if resp.status_code == 429:
                    backoff = 10 * (2 ** attempt)
                    logger.warning(
                        "Rate-limited on %s — sleeping %ss (attempt %s/%s)",
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
                    "HTTP %s on %s — retry %s/%s",
                    exc.response.status_code, path, attempt + 1, retries,
                )
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"Request failed after {retries} retries: {path}")

    async def _get_paginated(
        self, path: str, results_key: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Paginate through a list endpoint, collecting all results."""
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 250

        while True:
            merged = {"limit": limit, "offset": offset, **(params or {})}
            data = await self._get(path, merged)
            page_items = data.get(results_key, [])
            items.extend(page_items)

            pagination = data.get("pagination", {})
            if "count" not in pagination:
                break
            if offset + limit >= pagination["count"]:
                break
            offset += limit

        return items

    async def get_session_votes(
        self, congress: int, session: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all House roll call votes for a congress/session.
        Paginates automatically.
        Returns raw vote dicts from the API.
        """
        votes = await self._get_paginated(
            f"/house-vote/{congress}/{session}",
            results_key="houseRollCallVotes",
        )
        logger.info(
            "House votes: fetched %d votes for %dth Congress, session %d",
            len(votes), congress, session,
        )
        return votes

    async def get_vote_detail(
        self, congress: int, session: int, vote_number: int
    ) -> dict[str, Any]:
        """Fetch detail for a single House vote (question, party totals)."""
        data = await self._get(f"/house-vote/{congress}/{session}/{vote_number}")
        return data.get("houseRollCallVote", data)

    async def get_vote_members(
        self, congress: int, session: int, vote_number: int
    ) -> list[dict[str, Any]]:
        """
        Fetch per-member vote positions for a single House vote.
        The members endpoint returns all members in one response (no pagination).
        """
        data = await self._get(
            f"/house-vote/{congress}/{session}/{vote_number}/members",
        )
        container = data.get("houseRollCallVoteMemberVotes", data)
        return container.get("results", [])

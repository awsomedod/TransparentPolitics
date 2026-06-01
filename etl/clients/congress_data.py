"""
Congress.gov supplementary data client.

Fetches bill, nomination, treaty, and amendment metadata from the
Congress.gov API v3 — used to enrich vote records with context about
what was being voted on.

All endpoints share the same auth, rate limiting, and retry logic.
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.congress.gov/v3"
_DEFAULT_CAP = 4_000

# Map the various bill type strings from House API and Senate XML
# to the Congress.gov bill API path format.
BILL_TYPE_MAP: dict[str, str] = {
    "hr": "hr",
    "h.r": "hr",
    "h.r.": "hr",
    "s": "s",
    "s.": "s",
    "hres": "hres",
    "h.res": "hres",
    "h.res.": "hres",
    "sres": "sres",
    "s.res": "sres",
    "s.res.": "sres",
    "hjres": "hjres",
    "h.j.res": "hjres",
    "h.j.res.": "hjres",
    "sjres": "sjres",
    "s.j.res": "sjres",
    "s.j.res.": "sjres",
    "hconres": "hconres",
    "h.con.res": "hconres",
    "h.con.res.": "hconres",
    "sconres": "sconres",
    "s.con.res": "sconres",
    "s.con.res.": "sconres",
}


class CongressDataClient:
    """
    Async client for Congress.gov supplementary data endpoints.

    Usage:
        async with CongressDataClient(api_key="...") as client:
            bill = await client.get_bill(119, "hr", "3424")
            nom = await client.get_nomination(119, "373")
            treaty = await client.get_treaty(119, "1")
            amend = await client.get_amendment(119, "samdt", "2137")
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

    async def __aenter__(self) -> "CongressDataClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _get(
        self, path: str, params: dict[str, Any] | None = None, *, retries: int = 3
    ) -> Any:
        """Rate-limited GET with retry on 429 and transient errors."""
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

    async def get_bill(
        self, congress: int, bill_type: str, bill_number: str
    ) -> dict[str, Any]:
        """Fetch a single bill/resolution. bill_type should be api-format (e.g. 'hr')."""
        data = await self._get(f"/bill/{congress}/{bill_type}/{bill_number}")
        return data.get("bill", data)

    async def get_nomination(self, congress: int, number: str) -> dict[str, Any]:
        """Fetch a single nomination."""
        data = await self._get(f"/nomination/{congress}/{number}")
        return data.get("nomination", data)

    async def get_treaty(self, congress: int, number: str) -> dict[str, Any]:
        """Fetch a single treaty."""
        data = await self._get(f"/treaty/{congress}/{number}")
        return data.get("treaty", data)

    async def get_amendment(
        self, congress: int, amend_type: str, amend_number: str
    ) -> dict[str, Any]:
        """Fetch a single amendment. amend_type is e.g. 'samdt' or 'hamdt'."""
        data = await self._get(
            f"/amendment/{congress}/{amend_type}/{amend_number}"
        )
        return data.get("amendment", data)

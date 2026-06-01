"""
Senate roll call votes client.

Fetches Senate vote data from senate.gov XML files. There is no Senate
vote endpoint in the Congress.gov API (confirmed April 2026).

Data sources:
    Vote menu (list):  senate.gov/legislative/LIS/roll_call_lists/vote_menu_{congress}_{session}.xml
    Individual vote:   senate.gov/legislative/LIS/roll_call_votes/
                      vote{congress}{session}/vote_{congress}_{session}_{number}.xml

No auth required. No documented rate limit (but we throttle to be polite).
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.senate.gov/legislative/LIS"
_POLITE_DELAY = 0.5  # seconds between requests — no rate limit but be respectful


class SenateVotesClient:
    """
    Async client for Senate roll call vote XML files.

    Usage:
        async with SenateVotesClient() as client:
            vote_list = await client.get_session_votes(119, 1)
            vote = await client.get_vote(119, 1, 1)
    """

    def __init__(self) -> None:
        self._last_request_at: float = 0.0
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "TransparentPolitics/0.1 (civic data project)"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "SenateVotesClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _get_xml(self, url: str, *, retries: int = 3) -> ET.Element:
        """Fetch and parse an XML document with polite throttling and retry."""
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_request_at
        gap = _POLITE_DELAY - elapsed
        if gap > 0:
            await asyncio.sleep(gap)

        for attempt in range(retries):
            self._last_request_at = loop.time()
            try:
                resp = await self._http.get(url)
                resp.raise_for_status()
                return ET.fromstring(resp.text)
            except (httpx.HTTPStatusError, httpx.ConnectError, ET.ParseError) as exc:
                if attempt == retries - 1:
                    raise
                logger.warning(
                    "Senate XML fetch error on %s — retry %s/%s: %s",
                    url, attempt + 1, retries, exc,
                )
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"Senate XML fetch failed after {retries} retries: {url}")

    async def get_session_votes(
        self, congress: int, session: int
    ) -> list[dict[str, Any]]:
        """
        Fetch the vote menu for a senate session — returns a summary list
        of all votes (number, date, question, result, yea/nay counts).
        """
        url = (
            f"{_BASE_URL}/roll_call_lists"
            f"/vote_menu_{congress}_{session}.xml"
        )
        root = await self._get_xml(url)

        votes: list[dict[str, Any]] = []
        for vote_el in root.findall(".//vote"):
            votes.append({
                "vote_number": int(vote_el.findtext("vote_number", "0")),
                "vote_date": (vote_el.findtext("vote_date") or "").strip(),
                "issue": (vote_el.findtext("issue") or "").strip(),
                "question": (vote_el.findtext("question") or "").strip(),
                "result": (vote_el.findtext("result") or "").strip(),
                "title": (vote_el.findtext("title") or "").strip(),
                "yeas": int(vote_el.findtext("vote_tally/yeas") or 0),
                "nays": int(vote_el.findtext("vote_tally/nays") or 0),
            })

        logger.info(
            "Senate votes: fetched %d vote summaries for %dth Congress, session %d",
            len(votes), congress, session,
        )
        return votes

    async def get_vote(
        self, congress: int, session: int, vote_number: int
    ) -> dict[str, Any]:
        """
        Fetch a single Senate vote with full detail including member positions.
        Returns a dict with vote metadata and a 'members' list.
        """
        padded = f"{vote_number:05d}"
        url = (
            f"{_BASE_URL}/roll_call_votes"
            f"/vote{congress}{session}"
            f"/vote_{congress}_{session}_{padded}.xml"
        )
        root = await self._get_xml(url)

        # Parse vote metadata
        vote: dict[str, Any] = {
            "congress": int(root.findtext("congress") or congress),
            "session": int(root.findtext("session") or session),
            "vote_number": int(root.findtext("vote_number") or vote_number),
            "vote_date": (root.findtext("vote_date") or "").strip(),
            "question": (root.findtext("question") or "").strip(),
            "vote_question_text": (root.findtext("vote_question_text") or "").strip(),
            "vote_document_text": (root.findtext("vote_document_text") or "").strip(),
            "vote_result": (root.findtext("vote_result") or "").strip(),
            "vote_title": (root.findtext("vote_title") or "").strip(),
            "majority_requirement": (root.findtext("majority_requirement") or "").strip(),
            "yeas": int(root.findtext("count/yeas") or 0),
            "nays": int(root.findtext("count/nays") or 0),
            "present": int(root.findtext("count/present") or 0),
            "absent": int(root.findtext("count/absent") or 0),
        }

        # Parse document reference (bill/resolution)
        doc_el = root.find("document")
        if doc_el is not None:
            vote["document"] = {
                "type": (doc_el.findtext("document_type") or "").strip(),
                "number": (doc_el.findtext("document_number") or "").strip(),
                "name": (doc_el.findtext("document_name") or "").strip(),
                "title": (doc_el.findtext("document_title") or "").strip(),
            }

        # Parse amendment reference
        amend_el = root.find("amendment")
        if amend_el is not None:
            amend_num = (amend_el.findtext("amendment_number") or "").strip()
            if amend_num:
                vote["amendment"] = {
                    "number": amend_num,
                    "purpose": (amend_el.findtext("amendment_purpose") or "").strip(),
                }

        # Parse member votes
        members: list[dict[str, Any]] = []
        members_el = root.find("members")
        if members_el is not None:
            for m in members_el.findall("member"):
                members.append({
                    "first_name": (m.findtext("first_name") or "").strip(),
                    "last_name": (m.findtext("last_name") or "").strip(),
                    "party": (m.findtext("party") or "").strip(),
                    "state": (m.findtext("state") or "").strip(),
                    "vote_cast": (m.findtext("vote_cast") or "").strip(),
                    "lis_member_id": (m.findtext("lis_member_id") or "").strip(),
                })

        vote["members"] = members
        return vote

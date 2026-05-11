"""
Unit tests for clients/congress_gov.py.

All HTTP calls are mocked — no network access, no API key required.
Fixtures are captured from the real API; see scripts/fetch_fixtures.py.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.congress_gov import (
    CongressGovClient,
    MemberDetail,
    MemberSummary,
    _MemberDetailResponse,
    _MemberListResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Model parsing — verified against real API fixtures
# ---------------------------------------------------------------------------

class TestMemberListParsing:
    def test_parses_all_members(self) -> None:
        data = load("congress_gov_member_list.json")
        result = _MemberListResponse.model_validate(data)
        assert len(result.members) == 5

    def test_pagination_count(self) -> None:
        data = load("congress_gov_member_list.json")
        result = _MemberListResponse.model_validate(data)
        assert result.pagination.count == 536

    def test_member_fields(self) -> None:
        data = load("congress_gov_member_list.json")
        members = _MemberListResponse.model_validate(data).members
        booker = next(m for m in members if m.bioguide_id == "B001288")
        assert booker.name == "Booker, Cory A."
        assert booker.party_name == "Democratic"
        assert booker.state == "New Jersey"   # full name, not 2-letter code
        assert booker.district is None         # senator

    def test_house_member_has_district(self) -> None:
        data = load("congress_gov_member_list.json")
        members = _MemberListResponse.model_validate(data).members
        mejia = next(m for m in members if m.bioguide_id == "M001246")
        assert mejia.district == 11

    def test_extra_fields_ignored(self) -> None:
        """depiction, updateDate, url etc. should not cause a parse error."""
        data = load("congress_gov_member_list.json")
        _MemberListResponse.model_validate(data)  # must not raise


class TestMemberDetailParsing:
    def setup_method(self) -> None:
        self.data = load("congress_gov_member_detail.json")
        self.detail = _MemberDetailResponse.model_validate(self.data).member

    def test_bioguide_id(self) -> None:
        assert self.detail.bioguide_id == "M000355"

    def test_names(self) -> None:
        assert self.detail.direct_order_name == "Mitch McConnell"
        assert self.detail.inverted_order_name == "McConnell, Mitch"

    def test_birth_year_coerced_from_string(self) -> None:
        # API returns "1942" as a string — validator must coerce to int.
        assert self.detail.birth_year == 1942
        assert isinstance(self.detail.birth_year, int)

    def test_death_year_is_none_for_living_member(self) -> None:
        assert self.detail.death_year is None

    def test_state_is_full_name(self) -> None:
        assert self.detail.state == "Kentucky"

    def test_party_history(self) -> None:
        assert len(self.detail.party_history) == 1
        assert self.detail.party_history[0].party_name == "Republican"
        assert self.detail.party_history[0].party_abbreviation == "R"

    def test_current_party_name(self) -> None:
        assert self.detail.current_party_name == "Republican"

    def test_terms_parsed(self) -> None:
        # McConnell has served since 1985 — many terms.
        assert len(self.detail.terms) > 1

    def test_current_term_has_no_end_year(self) -> None:
        # The latest term (119th Congress) has no endYear in the API response.
        current = self.detail.current_term
        assert current is not None
        assert current.end_year is None
        assert current.member_type == "Senator"

    def test_display_name(self) -> None:
        assert self.detail.display_name == "Mitch McConnell"

    def test_canonical_name(self) -> None:
        assert self.detail.canonical_name == "McConnell, Mitch"


# ---------------------------------------------------------------------------
# Pagination logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_members_paginates() -> None:
    """Client must keep fetching until offset >= pagination.count.

    Use 251 total members so the first page (limit=250) doesn't satisfy
    the stop condition and a second call is required.
    """
    def make_member(n: int) -> dict:
        return {"bioguideId": f"A{n:06d}", "name": f"Member, {n}"}

    page1 = {
        "members": [make_member(i) for i in range(250)],
        "pagination": {"count": 251},
    }
    page2 = {
        "members": [make_member(250)],
        "pagination": {"count": 251},
    }

    async def fake__get(path: str, params: dict | None = None, **_: object) -> dict:
        offset = (params or {}).get("offset", 0)
        return page1 if offset == 0 else page2

    client = CongressGovClient("test-key", requests_per_hour=100_000)
    client._get = fake__get  # type: ignore[method-assign]

    members = await client.get_current_members()
    assert len(members) == 251
    assert members[0].bioguide_id == "A000000"
    assert members[-1].bioguide_id == "A000250"
    await client.close()


# ---------------------------------------------------------------------------
# Retry on 429
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_retries_on_429() -> None:
    """Client must retry after a 429 and eventually succeed."""
    attempts: list[int] = []

    success_response = {
        "member": {
            "bioguideId": "X000001",
            "directOrderName": "Test Member",
            "partyHistory": [],
            "terms": [],
        }
    }

    async def fake_get(path: str, params: dict, **_) -> MagicMock:
        attempts.append(1)
        mock = MagicMock()
        if len(attempts) < 2:
            mock.status_code = 429
            mock.raise_for_status = MagicMock()
        else:
            mock.status_code = 200
            mock.json.return_value = success_response
            mock.raise_for_status = MagicMock()
        return mock

    client = CongressGovClient("test-key", requests_per_hour=100_000)
    client._http.get = fake_get  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        detail = await client.get_member_detail("X000001")

    assert detail.bioguide_id == "X000001"
    assert len(attempts) == 2   # one 429, one success
    await client.close()

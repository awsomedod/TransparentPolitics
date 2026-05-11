"""
Unit tests for clients/unitedstates.py.
All HTTP calls are mocked. Fixture is captured from the real source.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.unitedstates import LegislatorIds, LegislatorRecord, UnitedStatesClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestLegislatorRecordParsing:
    def setup_method(self) -> None:
        raw = json.loads(load("unitedstates_legislators_current_sample.json"))
        self.records = [LegislatorRecord.model_validate(r) for r in raw]

    def test_parses_five_records(self) -> None:
        assert len(self.records) == 5

    def test_cantwell_ids(self) -> None:
        cantwell = next(r for r in self.records if r.id.bioguide == "C000127")
        assert cantwell.id.thomas == "00172"
        assert "S8WA00194" in cantwell.id.fec
        assert cantwell.id.opensecrets == "N00007836"
        assert cantwell.id.wikidata == "Q22250"
        assert cantwell.id.ballotpedia == "Maria Cantwell"

    def test_fec_is_list(self) -> None:
        # Cantwell has two FEC IDs — verify list type
        cantwell = next(r for r in self.records if r.id.bioguide == "C000127")
        assert isinstance(cantwell.id.fec, list)
        assert len(cantwell.id.fec) == 2

    def test_icpsr_is_int(self) -> None:
        cantwell = next(r for r in self.records if r.id.bioguide == "C000127")
        assert isinstance(cantwell.id.icpsr, int)

    def test_extra_fields_ignored(self) -> None:
        """The full YAML has name, bio, terms, social — all should be silently dropped."""
        raw = [{"id": {"bioguide": "Z999999"}, "name": {"first": "Extra", "last": "Fields"}}]
        records = [LegislatorRecord.model_validate(r) for r in raw]
        assert records[0].id.bioguide == "Z999999"


@pytest.mark.asyncio
async def test_get_current_legislators_parses_yaml() -> None:
    """Client downloads YAML, parses it, and returns LegislatorRecord list."""
    # Minimal valid YAML that matches the real file structure
    yaml_text = """\
- id:
    bioguide: T000001
    thomas: "12345"
    fec:
      - H2TX00001
    icpsr: 99001
    opensecrets: N00099001
    votesmart: 99001
    ballotpedia: Test Member
    wikipedia: Test Member
    wikidata: Q9999999
    google_entity_id: kg:/m/test
  name:
    first: Test
    last: Member
"""

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = yaml_text

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("clients.unitedstates.httpx.AsyncClient", return_value=mock_client):
        client = UnitedStatesClient()
        records = await client.get_current_legislators()

    assert len(records) == 1
    assert records[0].id.bioguide == "T000001"
    assert records[0].id.fec == ["H2TX00001"]
    assert records[0].id.wikidata == "Q9999999"

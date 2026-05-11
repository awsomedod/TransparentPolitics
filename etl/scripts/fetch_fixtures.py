"""
One-off script: fetch real Congress.gov API responses and save them as
test fixtures. Run once to capture the actual response shape, then commit
the fixtures so tests can run offline in CI.

Usage (from etl/):
    python scripts/fetch_fixtures.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running from the etl/ directory without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.congress_gov import CongressGovClient
from clients.unitedstates import UnitedStatesClient

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
API_KEY = os.environ.get("CONGRESS_GOV_API_KEY", "")

# A known stable bioguide_id to use for the detail fixture.
# Mitch McConnell — long-serving senator, record won't disappear.
SAMPLE_BIOGUIDE_ID = "M000355"


async def main() -> None:
    if not API_KEY:
        print("ERROR: CONGRESS_GOV_API_KEY is not set.")
        print("Set it in your .env or export it before running this script.")
        sys.exit(1)

    FIXTURES.mkdir(parents=True, exist_ok=True)

    async with CongressGovClient(API_KEY) as client:
        # ── 1. Member list (first page only — 250 members) ──────────────────
        print("Fetching member list (first page)…")
        import httpx
        resp = await client._http.get(
            "/member",
            params={
                "api_key": API_KEY,
                "currentMember": "true",
                "limit": 5,   # small slice — enough to validate the shape
                "offset": 0,
            },
        )
        resp.raise_for_status()
        list_fixture = resp.json()
        out = FIXTURES / "congress_gov_member_list.json"
        out.write_text(json.dumps(list_fixture, indent=2))
        print(f"  Saved {out}  ({len(list_fixture.get('members', []))} members)")

        # ── 2. Member detail ─────────────────────────────────────────────────
        print(f"Fetching member detail for {SAMPLE_BIOGUIDE_ID}…")
        detail = await client.get_member_detail(SAMPLE_BIOGUIDE_ID)
        raw_resp = await client._http.get(
            f"/member/{SAMPLE_BIOGUIDE_ID}",
            params={"api_key": API_KEY},
        )
        raw_resp.raise_for_status()
        out = FIXTURES / "congress_gov_member_detail.json"
        out.write_text(json.dumps(raw_resp.json(), indent=2))
        print(f"  Saved {out}  (bioguide_id={detail.bioguide_id})")

    # ── 3. unitedstates legislators-current ──────────────────────────────────
    print("Fetching unitedstates/congress-legislators YAML (first 5 rows)…")
    us_client = UnitedStatesClient()
    records = await us_client.get_current_legislators()
    sample = [r.model_dump() for r in records[:5]]
    out = FIXTURES / "unitedstates_legislators_current_sample.json"
    out.write_text(json.dumps(sample, indent=2))
    print(f"  Saved {out}  ({len(records)} total records, saved first 5)")

    print("\nDone. Commit the files in etl/tests/fixtures/ to the repo.")


if __name__ == "__main__":
    asyncio.run(main())

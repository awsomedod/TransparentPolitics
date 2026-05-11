# Data Source Plan — Congress Members (Milestone 1)

**Goal:** Ingest all current members of the 119th US Congress with biographical data,
current office, party affiliation, and cross-source IDs, and keep that data current on a
nightly schedule.

---

## Candidate Sources Evaluated

| Source | Operator | Type | License |
|---|---|---|---|
| Congress.gov API | Library of Congress | REST API | US Gov public domain |
| `unitedstates/congress-legislators` | Open-source community | Bulk YAML download | Public domain (Unlicense) |
| CIV.IQ API | CIV.IQ (third party) | REST API | MIT |
| BioGuide (HTML) | Library of Congress | HTML scrape | US Gov public domain |

### Why CIV.IQ is excluded

CIV.IQ is an aggregator that itself ingests Congress.gov, OpenStates, and BioGuide.
Going through a third-party intermediary adds a dependency on their uptime, their
normalization choices, and their data freshness. Using primary sources directly gives us
cleaner provenance, no rate-limit dependency on a third party, and full control over
normalization decisions. CIV.IQ may be reconsidered for state-level data (Milestone 6+)
where primary sources are fragmented, but not for federal members.

### Why BioGuide HTML scraping is excluded

BioGuide's main value is the canonical `bioguide_id`, which Congress.gov already returns
in its API responses. The BioGuide HTML interface is not a stable API and has no
versioning guarantee. The Congress.gov API is the right way to get this data.

---

## Sources Selected

### Source 1 — Congress.gov API

- **URL:** `https://api.congress.gov/v3/`
- **Operator:** Library of Congress (official US government)
- **Auth:** Free API key — register at <https://api.congress.gov/sign-up/>
- **Rate limit:** 5,000 requests/hour
- **Pagination:** `offset` + `limit` (max 250 per page)
- **Format:** JSON
- **License:** US government work, public domain
- **Attribution required:** Yes — "Data provided by the Library of Congress Congress.gov API"

**Why primary:** This is the Library of Congress's own system. Congress.gov is the
authoritative source for all federal legislative data. Every other aggregator (GovTrack,
ProPublica, Ballotpedia) ultimately derives from this or from the underlying THOMAS system
it replaced.

**Endpoints used:**

| Endpoint | Purpose |
|---|---|
| `GET /v3/member?currentMember=true&limit=250` | Paginate all current members |
| `GET /v3/member/{bioguideId}` | Full member detail (bio, state, district, party, terms) |

**Fields ingested and schema mapping:**

| Congress.gov field | Our field | Table |
|---|---|---|
| `bioguideId` | `bioguide_id` | `persons` |
| `name` (inverted: "Last, First") | `canonical_name` | `persons` |
| `directOrderName` (if present) | `display_name` | `persons` |
| `birthYear` | `birth_date` (Jan 1 of year — year only) | `persons` |
| `deathYear` | `death_date` (Jan 1 of year — year only) | `persons` |
| `partyName` | normalized → `name`, `short_name` | `parties` |
| `state` (2-letter code) | resolved → `jurisdiction_id` | `officeholders` |
| `district` (number) | `district` (added in M2 geospatial) | `officeholders` |
| `terms[].startYear` | `start_date` | `officeholders` |
| `terms[].endYear` | `end_date` | `officeholders` |
| `terms[].memberType` | resolved → `office_id` | `officeholders` |

**Fields we do NOT ingest (and why):**

| Congress.gov field | Reason skipped |
|---|---|
| `sponsoredLegislation` | Covered by Milestone 2 (votes pipeline) |
| `cosponsoredLegislation` | Covered by Milestone 2 |
| `leadership` (caucus roles) | Added in Phase 2 enrichment |
| `officialWebsiteUrl` | Stored in `person_external_ids` as `source_name="website"` |
| `imageUrl` | Phase 2 — portrait storage in MinIO |

---

### Source 2 — `unitedstates/congress-legislators` (bulk YAML)

- **URL:** `https://github.com/unitedstates/congress-legislators`
- **Operator:** Open-source community project (maintained by contributors incl. ex-Sunlight Foundation)
- **Raw file URL:** `https://unitedstates.io/congress-legislators/legislators-current.json`
- **Auth:** None
- **Rate limit:** None (static file download)
- **Format:** JSON (also available as YAML)
- **License:** Public domain (Unlicense)
- **Attribution required:** Recommended — "Member ID data from unitedstates/congress-legislators"

**Why used alongside Congress.gov:**

Congress.gov's API returns `bioguide_id` but does not return all cross-source IDs in a
single call (FEC candidate ID, ICPSR, OpenSecrets, Ballotpedia slug, etc.). The
`legislators-current.json` file from this project is the canonical cross-reference table
for federal legislators — it maps `bioguide_id` to every other ID system in one place.
Many trusted projects (FiveThirtyEight, ProPublica, GovTrack) use this as their ID
backbone. It is updated within hours of changes (new members sworn in, corrections, etc.).

This source is derived (the maintainers pull from Congress.gov, FEC, and BioGuide), but
its cross-ID mapping is not available in any single primary source in one API call, making
it the practical standard.

**Fields ingested from this source only (all go into `person_external_ids`):**

| legislators-current field | `source_name` value | Notes |
|---|---|---|
| `id.fec` (array) | `"fec"` | One row per FEC ID; candidates can have multiple |
| `id.thomas` | `"thomas"` | Legacy THOMAS system ID |
| `id.icpsr` | `"icpsr"` | Political science database ID |
| `id.opensecrets` | `"opensecrets"` | OpenSecrets.org profile ID |
| `id.votesmart` | `"votesmart"` | VoteSmart.org ID |
| `id.ballotpedia` | `"ballotpedia"` | Ballotpedia article slug |
| `id.wikipedia` | `"wikipedia"` | Wikipedia article title |
| `id.wikidata` | `"wikidata"` | Wikidata QID (also stored on `persons.wikidata_qid`) |
| `id.google_entity_id` | `"google_entity_id"` | Google Knowledge Graph entity ID |

**Fields we do NOT ingest from this source:**

| Field | Reason |
|---|---|
| `bio.gender` | Not surfaced in UI; low priority for Phase 1 |
| `bio.religion` | Not surfaced in UI; privacy concern |
| `social.twitter` / `facebook` | Phase 2 social enrichment |
| `terms[*].url` | Official website URL stored in `person_external_ids` from Congress.gov |

---

## Entity Resolution Strategy

`bioguide_id` is the join key. Every member returned by Congress.gov has a `bioguide_id`.
Every row in `legislators-current.json` has a `bioguide_id` under `id.bioguide`. The
pipeline merges the two sources on this key:

1. Ingest Congress.gov members list → upsert `persons` (keyed on `bioguide_id`)
2. Ingest Congress.gov member detail → upsert `officeholders`, upsert `parties`
3. Download `legislators-current.json` → match on `bioguide_id` → upsert `person_external_ids`

If a member appears in `legislators-current.json` but NOT in the Congress.gov current
member list, they are skipped (they are not a current member). The Congress.gov list is
the authoritative source for "is this person currently serving".

---

## Party Normalization

Congress.gov `partyName` values observed in the 119th Congress:

| Raw value | Canonical `name` | `short_name` |
|---|---|---|
| `"Democratic"` | `"Democrat"` | `"D"` |
| `"Republican"` | `"Republican"` | `"R"` |
| `"Independent"` | `"Independent"` | `"I"` |

Normalization is a deterministic string lookup table in the ETL code, not a hardcoded
database seed. If a new party name appears that isn't in the lookup table, the pipeline
logs an `IngestError` and the row is skipped rather than silently inventing a new party.
A human reviews the error, updates the lookup table, and re-runs. This ensures no party
is ever created by accident.

`color_hex` on the `Party` model is intentionally left `NULL` for all programmatically
created parties. It is a UI display hint only and will be set manually by a project
maintainer if and when the UI needs it.

---

## Office Resolution

Congress.gov `terms[].memberType` values:

| Raw value | `offices.title` | `offices.chamber` |
|---|---|---|
| `"Senator"` | `"US Senator"` | `"senate"` |
| `"Representative"` | `"US Representative"` | `"house"` |
| `"Delegate"` | `"US Delegate"` | `"house"` |
| `"Resident Commissioner"` | `"US Resident Commissioner"` | `"house"` |

The federal jurisdiction row (`jurisdictions.type = "federal"`, `jurisdictions.name =
"United States"`) and all state jurisdiction rows are upserted by the pipeline on first
run, not seeded by migration. States are resolved from the 2-letter `state` code using the
standard 50-state + DC + territories lookup.

---

## Ingest Schedule

| Job | Trigger | Rationale |
|---|---|---|
| Full member list refresh | Nightly at 02:00 UTC | Catches special elections, deaths, resignations |
| Member detail refresh | Nightly at 02:15 UTC | Updates party changes, new terms |
| ID cross-reference refresh | Nightly at 02:30 UTC | `legislators-current.json` is updated same-day |

All three are Dagster assets in a single `congress_members` job. They run sequentially.
Manual trigger is always available via the Dagster UI for out-of-cycle refreshes (e.g.,
right after a major election).

---

## Raw Data Storage

All API responses are stored to MinIO before any transformation, following the
`raw/{source}/{YYYY-MM-DD}/{filename}.json` path convention. This means:

- Any transformation bug can be replayed against the original response without re-fetching
- The ingest timestamp is part of the path, creating an implicit audit trail
- Storage is cheap; raw Congress.gov member data is ~5 MB total

---

## Known Limitations

1. **Birth/death year only:** Congress.gov returns `birthYear` and `deathYear` as 4-digit
   integers, not full dates. We store `YYYY-01-01` as a placeholder and note in the UI
   that only the year is known.
2. **Historical terms:** Congress.gov returns all terms a member has served, not just the
   current one. We ingest all terms into `officeholders` with `is_current = true` for the
   active term only.
3. **District numbers:** House members have a `district` field (1–N or 0 for at-large).
   This is stored but not joined to a geographic boundary until Milestone 6 (geospatial).
4. **Party changes mid-term:** If a member switches parties, Congress.gov updates
   `partyName` on the next API call. The nightly job will pick this up and update the
   `officeholders.party_id` FK. No historical party record is kept in Phase 1.

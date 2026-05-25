# Milestone 2 — Votes & Legislation

> **Status:** Planning
> Last updated: 2026-05-25

---

## Goal

Track every roll call vote in the 119th Congress (both chambers), linked to
the underlying legislation, nomination, treaty, or amendment where applicable.
Display voting records on politician profile pages.

---

## Data Sources

| Source | Chamber | Format | Auth | What it provides |
|--------|---------|--------|------|-----------------|
| Congress.gov API `/v3/house-vote` | House | JSON | API key (existing) | Roll call votes + per-member positions |
| Senate.gov LIS XML | Senate | XML | None (public) | Roll call votes + per-member positions |
| Congress.gov API `/v3/bill` | Both | JSON | API key | Bill/resolution metadata (title, sponsor, status, subjects) |
| Congress.gov API `/v3/nomination` | Senate | JSON | API key | Nominee name, position, committee, result |
| Congress.gov API `/v3/treaty` | Senate | JSON | API key | Treaty title, topic, submitted date, result |
| Congress.gov API `/v3/amendment` | Both | JSON | API key | Amendment purpose, sponsor, parent bill |

### Primary sources

- **House votes:** Congress.gov API — operated by the Library of Congress in
  partnership with the Office of the Clerk. Official government record.
  Available from 116th Congress (2019) onward.
- **Senate votes:** Senate.gov XML — published by the Senate Secretary's office.
  Congress.gov does not have a Senate vote API (confirmed April 2026).

---

## Scope

- **119th Congress only** (2025–2026, sessions 1 and 2)
- **All vote types:** bill passage, amendments, cloture, nominations, treaties,
  procedural, motions, veto overrides
- **All amendments** that went to a roll call vote (plus their metadata)
- **No full bill text ingestion** — store title, status, sponsor, subjects;
  link to full text via URL

---

## Schema (Tentative)

These schemas are tentative. We will first snapshot real data from each source
and examine its structure before finalizing the tables.

### `legislation`

Stores bills and resolutions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `bill_number` | String | e.g. "HR 1234", "S.J.Res. 116" |
| `bill_type` | String | e.g. "hr", "s", "sjres", "hjres", "sres", "hres", "sconres", "hconres" |
| `congress` | Integer | e.g. 119 |
| `title` | Text | Short title from Congress.gov |
| `introduced_date` | Date nullable | |
| `status` | String nullable | e.g. "Became Law", "Passed Senate", "In Committee" |
| `sponsor_id` | UUID FK → persons nullable | Primary sponsor |
| `subject_areas` | Text nullable | Comma-separated or JSON array |
| `source_url` | Text | Congress.gov URL |
| `data_source_id` | UUID FK → data_sources | |

### `nominations`

Stores presidential nominations (Senate-confirmed positions).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `nomination_number` | String | e.g. "PN373" |
| `congress` | Integer | |
| `description` | Text | Full description of the nomination |
| `nominee_name` | String nullable | Name of the nominee |
| `position` | String nullable | Position they're nominated for |
| `received_date` | Date nullable | When Senate received it |
| `result` | String nullable | e.g. "Confirmed", "Withdrawn" |
| `source_url` | Text | |
| `data_source_id` | UUID FK → data_sources | |

### `treaties`

Stores treaties submitted to the Senate.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `treaty_number` | String | e.g. "TD119-1" |
| `congress` | Integer | |
| `title` | Text | |
| `topic` | String nullable | |
| `submitted_date` | Date nullable | |
| `result` | String nullable | e.g. "Ratified", "Pending" |
| `resolution_text` | Text nullable | Text of resolution of ratification |
| `source_url` | Text | |
| `data_source_id` | UUID FK → data_sources | |

### `amendments`

Stores amendments to bills/resolutions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `amendment_number` | String | e.g. "SA 2137", "H.Amdt. 45" |
| `amendment_type` | String | e.g. "samdt", "hamdt" |
| `congress` | Integer | |
| `purpose` | Text nullable | What the amendment does |
| `sponsor_id` | UUID FK → persons nullable | Who proposed it |
| `legislation_id` | UUID FK → legislation nullable | Parent bill |
| `source_url` | Text | |
| `data_source_id` | UUID FK → data_sources | |

### `roll_call_votes`

One row per vote event. Links to at most one of legislation/nomination/
treaty/amendment (or none for pure procedural votes).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `vote_number` | Integer | Sequential within session |
| `congress` | Integer | |
| `session` | Integer | 1 or 2 |
| `chamber` | String | "House" or "Senate" |
| `vote_date` | DateTime | |
| `question` | Text | Procedural description of the action |
| `result` | String | e.g. "Passed", "Rejected", "Agreed to" |
| `yea_count` | Integer | |
| `nay_count` | Integer | |
| `not_voting_count` | Integer | |
| `source_url` | Text | Link to official vote record |
| `legislation_id` | UUID FK → legislation nullable | |
| `nomination_id` | UUID FK → nominations nullable | |
| `treaty_id` | UUID FK → treaties nullable | |
| `amendment_id` | UUID FK → amendments nullable | |
| `data_source_id` | UUID FK → data_sources | |

### `person_votes`

One row per member per vote.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `person_id` | UUID FK → persons | Joined via bioguide_id |
| `roll_call_vote_id` | UUID FK → roll_call_votes | |
| `position` | String | "Yea", "Nay", "Not Voting", "Present" |

Unique constraint on `(person_id, roll_call_vote_id)`.

---

## Increments

### Phase A — Snapshot First

Fetch raw data from all sources and save to MinIO. Examine the structure
before building the DB schema.

| # | Increment | What | Dependencies |
|---|-----------|------|-------------|
| A1 | House votes client | `etl/clients/house_votes.py` — Congress.gov API client for `/v3/house-vote`. Fetch 119th Congress vote list + per-vote member positions. | API key |
| A2 | House votes snapshot | Dagster asset: fetch all 119th House votes → snapshot to MinIO | A1 |
| A3 | Senate votes client | `etl/clients/senate_votes.py` — Parse Senate.gov XML. Fetch vote menu + per-vote XML. | None |
| A4 | Senate votes snapshot | Dagster asset: fetch all 119th Senate votes → snapshot to MinIO | A3 |
| A5 | Legislation client | Extend Congress.gov client for `/v3/bill`. Fetch bills referenced by votes. | API key |
| A6 | Legislation snapshot | Dagster asset: fetch bill metadata for all bills referenced in vote snapshots → MinIO | A5, A2, A4 |
| A7 | Nominations client | Congress.gov `/v3/nomination` — fetch 119th nominations → MinIO | API key |
| A8 | Treaties client | Congress.gov `/v3/treaty` — fetch 119th treaties → MinIO | API key |
| A9 | Amendments client | Congress.gov `/v3/amendment` — fetch 119th amendments → MinIO | API key |

**Checkpoint:** At this point, review all snapshots and finalize the schema.

### Phase B — Schema & Upsert

| # | Increment | What | Dependencies |
|---|-----------|------|-------------|
| B1 | Finalize schema | Review snapshot data, adjust tentative schema, write ORM models | Phase A complete |
| B2 | Alembic migration | Create all 6 new tables | B1 |
| B3 | Upsert asset | Read snapshots → upsert legislation, nominations, treaties, amendments, roll_call_votes, person_votes | B2 |

### Phase C — API & Frontend

| # | Increment | What | Dependencies |
|---|-----------|------|-------------|
| C1 | API endpoints | `GET /politicians/{id}/votes` (paginated, filterable by chamber/congress), `GET /votes/{id}` (single vote detail) | B3 |
| C2 | Frontend votes tab | Votes section on profile page: recent votes with position, question, related bill title, result | C1 |

---

## Volume Estimates (119th Congress)

| Data | Approximate count |
|------|------------------|
| House roll call votes | ~300–500 per session |
| Senate roll call votes | ~550 per session (so far in 119th) |
| Person votes | ~(House votes × 435) + (Senate votes × 100) ≈ 200k–300k rows |
| Bills/resolutions referenced | ~500–1000 unique |
| Nominations | ~200–400 |
| Treaties | ~10–30 |
| Amendments | Several thousand |

Total ingest time will be dominated by rate limiting on Congress.gov
(4,000 req/hr cap). Estimated ~2–4 hours for full initial load.

---

## Open Questions

1. **Amendment scope:** Fetch only amendments that had roll call votes, or all
   amendments for the 119th Congress? (Current decision: all amendments.)
2. **Schema finalization:** Deferred until Phase A snapshots are reviewed.
3. **Incremental updates:** Nightly schedule to pick up new votes? Or manual
   trigger only for now?

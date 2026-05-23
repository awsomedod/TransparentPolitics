# TransparentPolitics — Build Status & Architecture

> **Living document.** Updated after every completed step.
> Last updated: 2026-05-23

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Architecture Overview](#architecture-overview)
3. [Infrastructure Services](#infrastructure-services)
4. [Database Schema](#database-schema)
5. [ETL Pipeline](#etl-pipeline)
6. [API Layer](#api-layer)
7. [Frontend](#frontend)
8. [Milestone Progress](#milestone-progress)
9. [Data Sources Registry](#data-sources-registry)
10. [Key Design Decisions](#key-design-decisions)

---

## Core Principles

These principles govern every implementation decision:

| Principle | Meaning |
|---|---|
| **Source-driven** | No data is manually seeded or invented. Every row traces to a real upstream source. |
| **Primary sources first** | Use official APIs (Congress.gov, FEC) before community aggregators, and community aggregators before scrapers. |
| **Citation-heavy** | Every record links to the `data_sources` row it came from via `data_source_id`. |
| **Deterministic only (Phase 1)** | No AI or ML in Phase 1. All transformations are rule-based and auditable. |
| **Politically neutral** | No editorial ratings, bias scores, or subjective classifications. |
| **Incremental** | Each step is small, reviewed, and committed before the next begins. |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        External Sources                         │
│   Congress.gov API    unitedstates/congress-legislators (YAML)  │
│   OpenFEC API         RSS feeds         ...future sources       │
└──────────────────────┬──────────────────────────────────────────┘
                       │  HTTP (httpx clients)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ETL Layer (Dagster)                      │
│                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────────────┐  │
│  │  clients/   │   │  assets/    │   │  Inline normalization │  │
│  │  (httpx +   │──▶│  (Dagster   │──▶│  (party names,        │  │
│  │  Pydantic)  │   │   assets)   │   │   state codes,        │  │
│  └─────────────┘   └──────┬──────┘   │   office titles)      │  │
│                           │          └──────────────────────┘  │
│                    ┌──────▼──────┐                              │
│                    │  Raw snap-  │  MinIO (S3-compatible)       │
│                    │  shots saved│  object storage              │
│                    └──────┬──────┘                              │
└───────────────────────────┼─────────────────────────────────────┘
                            │  SQLAlchemy (upsert)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PostgreSQL 16 + PostGIS                     │
│                                                                 │
│  parties  jurisdictions  offices  data_sources                  │
│  persons  person_external_ids  officeholders                    │
│  ingest_errors                                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │  SQLAlchemy (async)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                           │
│                                                                 │
│  GET /api/v1/politicians          (not yet built)               │
│  GET /api/v1/politicians/{id}     (not yet built)               │
│  ...more endpoints per milestone                                │
└──────────────────────┬──────────────────────────────────────────┘
                       │  HTTP / REST
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Frontend (Next.js 15)                         │
│                   placeholder scaffold only                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure Services

Defined in `infra/docker-compose.yml`. All run locally via Docker Desktop.

| Service | Image | Port | Purpose | Status |
|---|---|---|---|---|
| PostgreSQL | `postgis/postgis:16-3.4` | 5432 | Primary database | Running |
| Redis | `redis:7-alpine` | 6379 | Caching / future queuing | Running |
| MinIO | `minio/minio:latest` | 9000 / 9001 | Raw ETL snapshot storage | Running |
| OpenSearch | `opensearchproject/opensearch:2` | 9200 | Full-text search (future) | Running |

---

## Database Schema

All tables defined as SQLAlchemy ORM models in `backend/app/db/models/`.
Migration applied: `alembic/versions/62bb5cdc1ec8_001_phase1_schema.py`.

### Reference tables (lookup / seed data)

These are populated by the ETL pipeline on first run — never manually inserted.

#### `parties`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(100) UNIQUE | Canonical name e.g. `"Democrat"` |
| `short_name` | String(20) UNIQUE | e.g. `"D"` |
| `color_hex` | String(7) nullable | e.g. `"#0000FF"` |

#### `jurisdictions`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(200) | e.g. `"Kentucky"` |
| `type` | String(50) | `federal \| state \| county \| city` |
| `fips_code` | String(10) nullable | indexed |
| `parent_id` | UUID FK → jurisdictions | self-referential hierarchy |

#### `offices`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `title` | String(200) | e.g. `"US Senator"` |
| `level` | String(50) | `federal \| state \| local` |
| `chamber` | String(50) nullable | `house \| senate \| executive` |
| `jurisdiction_id` | UUID FK → jurisdictions | |

#### `data_sources`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(200) UNIQUE | e.g. `"Congress.gov API"` |
| `url` | Text | Canonical URL for the source |
| `type` | String(50) | `api \| bulk \| rss \| manual` |
| `license` | Text nullable | License text or SPDX identifier |
| `attribution_text` | Text nullable | Required attribution string |
| `last_fetched_at` | DateTime nullable | Updated by ETL on each successful run |
| `fetch_frequency` | String(50) nullable | e.g. `"nightly"` |

> **Note:** `bias_rating` and `credibility_rating` were intentionally excluded — these are subjective editorial judgments inconsistent with the political neutrality principle.

### Person tables

#### `persons`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Internal surrogate key |
| `canonical_name` | String(300) | `"Last, First"` — used for sorting and dedup |
| `display_name` | String(300) | `"First Last"` — used in UI |
| `birth_date` | Date nullable | |
| `death_date` | Date nullable | |
| `bioguide_id` | String(20) UNIQUE | **Primary entity key** for federal legislators |
| `fec_candidate_id` | String(20) nullable | indexed |
| `openstates_id` | String(50) nullable | indexed (future: state legislators) |
| `wikidata_qid` | String(30) nullable | indexed |
| `created_at` | DateTime | server default |
| `updated_at` | DateTime | auto-updated on write |

#### `person_external_ids`
Stores all additional cross-source IDs in a flexible key-value table.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `person_id` | UUID FK → persons | indexed |
| `source_name` | String(100) | e.g. `"opensecrets"`, `"votesmart"`, `"icpsr"` |
| `external_id` | String(200) | The actual ID value |

> Unique constraint on `(person_id, source_name)` — one ID per source per person.

#### `officeholders`
Time-bounded record of a person holding an office. One row per term.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `person_id` | UUID FK → persons | indexed |
| `office_id` | UUID FK → offices | |
| `party_id` | UUID FK → parties nullable | Party affiliation for this term |
| `jurisdiction_id` | UUID FK → jurisdictions nullable | State/district for this term |
| `start_date` | Date nullable | |
| `end_date` | Date nullable | |
| `is_current` | Boolean | indexed — drives "current members" queries |
| `data_source_id` | UUID FK → data_sources nullable | Provenance |

### System tables

#### `ingest_errors`
ETL error log. Every caught exception during pipeline execution is written here.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `source_name` | String(200) | Which data source caused the error |
| `asset_name` | String(200) | Which Dagster asset was running |
| `error_type` | String(200) | Exception class name |
| `message` | Text | Exception message |
| `raw_payload` | Text nullable | Raw data that triggered the error |
| `occurred_at` | DateTime | server default |

---

## ETL Pipeline

All ETL is implemented in the `etl/` package using **Dagster**.

### Package layout

```
etl/
├── repository.py              # Dagster Definitions entry point
├── workspace.yaml             # Dagster webserver config
├── clients/                   # HTTP clients for upstream sources
│   ├── congress_gov.py        # ✅ Congress.gov API v3
│   └── unitedstates.py        # ✅ unitedstates/congress-legislators YAML
├── assets/
│   └── congress/
│       └── members.py         # 🔲 TODO: main pipeline asset
├── tests/
│   ├── fixtures/              # Captured real API responses (JSON)
│   │   ├── congress_gov_member_list.json
│   │   ├── congress_gov_member_detail.json
│   │   └── unitedstates_legislators_current_sample.json
│   ├── test_congress_gov_client.py   # ✅ 24 tests passing
│   └── test_unitedstates_client.py   # ✅ (included in 24 above)
└── scripts/
    └── fetch_fixtures.py      # One-off script to refresh test fixtures from live APIs
```

### Client: `etl/clients/congress_gov.py`

**Source:** Congress.gov API v3 (official government API)
**Auth:** API key (stored in `.env` as `CONGRESS_GOV_API_KEY`)
**Rate limit:** 5,000 req/hr — client self-caps at 4,000 req/hr
**Retry:** Exponential backoff on HTTP 429 (10 s → 20 s → 40 s)

Pydantic models defined:

| Model | Maps to | Key fields |
|---|---|---|
| `MemberSummary` | `GET /v3/member` list item | `bioguide_id`, `name`, `party_name`, `state`, `district` |
| `MemberDetail` | `GET /v3/member/{id}` | `bioguide_id`, `birth_year`, `death_year`, `party_history`, `terms` |
| `TermItem` | item inside `MemberDetail.terms` | `chamber`, `member_type`, `congress`, `start_year`, `end_year`, `state_code` |
| `PartyHistoryItem` | item inside `MemberDetail.party_history` | `party_name`, `party_abbreviation`, `start_year` |

Key implementation notes:
- `birth_year` / `death_year` arrive as **strings** from the API (`"1942"`), not integers. A `field_validator` coerces them before model validation.
- `state` on `MemberSummary` is the **full state name** (e.g. `"Kentucky"`), not a 2-letter code. Normalization to `"KY"` happens in the asset.
- Pagination: the list endpoint caps at 250 per page; `get_current_members()` loops until `offset + limit >= pagination.count`.

### Client: `etl/clients/unitedstates.py`

**Source:** `unitedstates/congress-legislators` GitHub repository (community-maintained)
**Auth:** None (public GitHub raw URL)
**Rate limit:** None
**Format:** YAML, parsed with `pyyaml`

> **Why this source:** Congress.gov does not expose all cross-source IDs in a single call. This YAML file maps each `bioguide_id` to FEC IDs, ICPSR, OpenSecrets, VoteSmart, Ballotpedia, Wikipedia, and Wikidata. It is the industry-standard ID backbone used by GovTrack, FiveThirtyEight, and ProPublica.
>
> **Note on format change:** The project formerly served JSON via `theunitedstates.io` CDN (now offline, returns 410 Gone). The canonical source is now the YAML file on GitHub raw (`legislators-current.yaml`).

Pydantic models defined:

| Model | Key fields |
|---|---|
| `LegislatorIds` | `bioguide` (required), `fec` (list), `icpsr`, `opensecrets`, `votesmart`, `ballotpedia`, `wikipedia`, `wikidata`, `google_entity_id` |
| `LegislatorRecord` | `id: LegislatorIds` — only the ID block is parsed; all other fields (bio, terms, social) are intentionally ignored in favor of Congress.gov as primary source |

### Normalization rules (to be applied inline in the asset)

| Field | Raw value example | Canonical value |
|---|---|---|
| Party name | `"Democratic"` | `"Democrat"` |
| Party name | `"Republican"` | `"Republican"` |
| Party name | `"Independent"` | `"Independent"` |
| State | `"Kentucky"` | `"KY"` |
| State | `"California"` | `"CA"` |
| Office type | `"Senator"` | `"US Senator"` |
| Office type | `"Representative"` | `"US Representative"` |

### Ingest schedule

| Source | Frequency | Dagster asset |
|---|---|---|
| Congress.gov API | Nightly 2 AM | `etl/assets/congress/members.py` (TODO) |
| unitedstates/congress-legislators | Nightly 2 AM (same run) | Same asset |

---

## API Layer

**Framework:** FastAPI (async)
**Location:** `backend/app/`

| Endpoint | Status | Milestone |
|---|---|---|
| `GET /health` | ✅ Implemented | M0 |
| `GET /api/v1/politicians` | 🔲 TODO | M1 |
| `GET /api/v1/politicians/{id}` | 🔲 TODO | M1 |
| `GET /api/v1/politicians/{id}/votes` | 🔲 TODO | M2 |
| `GET /api/v1/votes/{id}` | 🔲 TODO | M2 |
| `GET /api/v1/politicians/{id}/finance` | 🔲 TODO | M3 |
| `GET /api/v1/news` | 🔲 TODO | M4 |
| `GET /api/v1/search` | 🔲 TODO | M4 |
| `GET /api/v1/search/autocomplete` | 🔲 TODO | M4 |

---

## Frontend

**Framework:** Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query
**Location:** `frontend/`

| Page | Status | Milestone |
|---|---|---|
| Root layout + placeholder home | ✅ Scaffold | M0 |
| Home / search | 🔲 TODO | M5 |
| Search results | 🔲 TODO | M5 |
| Politician profile (tabbed) | 🔲 TODO | M5 |
| Votes tab | 🔲 TODO | M5 |
| Finance tab | 🔲 TODO | M5 |
| `SourceCitation` component | 🔲 TODO | M5 |

---

## Milestone Progress

### Phase 1 — Federal MVP

| Milestone | Description | Status |
|---|---|---|
| **M0** | Dev infrastructure | ✅ Complete |
| **M1** | Congress members pipeline | 🔄 In Progress |
| **M2** | Votes & legislation | 🔲 Pending |
| **M3** | Campaign finance (FEC) | 🔲 Pending |
| **M4** | News & search | 🔲 Pending |
| **M5** | Frontend & deploy | 🔲 Pending |

### Milestone 0 — Dev Infrastructure ✅

| Step | What | Status |
|---|---|---|
| Git repo + docs | README, plan.md, phase1.md, .gitignore | ✅ |
| Docker services | postgres/postgis, redis, minio, opensearch | ✅ |
| Backend scaffold | FastAPI app, config, SQLAlchemy session, Alembic | ✅ |
| ETL scaffold | Dagster repo, pyproject.toml, package dirs | ✅ |
| Frontend scaffold | Next.js 15, Tailwind, shadcn/ui, TanStack Query | ✅ |
| CI | GitHub Actions: ruff, mypy, pytest, ESLint, tsc | ✅ |

### Milestone 1 — Congress Members Pipeline 🔄

| Step | What | Status |
|---|---|---|
| ORM models | Party, Jurisdiction, Office, DataSource, Person, PersonExternalId, Officeholder, IngestError | ✅ |
| Alembic migration | 001_phase1_schema — creates all 8 tables | ✅ |
| Data source docs | `docs/sources/congress-members.md` — source selection, field mappings, normalization rules | ✅ |
| ETL client: Congress.gov | Pydantic models, rate limiting, pagination, field validators | ✅ |
| ETL client: unitedstates | YAML fetch + parse, ID cross-reference models | ✅ |
| Test fixtures | Captured real API responses → JSON files | ✅ |
| Unit tests | 24 tests covering both clients — all passing | ✅ |
| Dagster asset: members | Fetch → MinIO → normalize → upsert → error log | 🔲 Next |
| FastAPI endpoints | `GET /api/v1/politicians`, `GET /api/v1/politicians/{id}` | 🔲 Pending |

---

## Data Sources Registry

Sources that are active, planned, or explicitly rejected.

| Source | Type | Auth | License | Used for | Status |
|---|---|---|---|---|---|
| [Congress.gov API v3](https://api.congress.gov/) | API | API key | Public domain | Member bio, terms, party history | ✅ Active |
| [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators) | Bulk YAML | None | Unlicense (public domain) | Cross-source ID mapping | ✅ Active |
| [OpenFEC API](https://api.open.fec.gov/) | API | API key | Public domain | Campaign finance | 🔲 M3 |
| RSS feeds (TBD) | RSS | None | Varies | Political news | 🔲 M4 |
| BioGuide HTML | Scrape | None | — | Member bio | ❌ Rejected — HTML scraping is fragile; Congress.gov API is the official replacement |
| CIV.IQ | Third-party aggregator | — | — | — | ❌ Rejected — secondary aggregator with no declared license; prefer primary sources |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `bioguide_id` as canonical entity key | Stable, official, cross-referenced by Congress.gov, FEC, GovTrack, ProPublica. Unambiguous identity anchor for federal legislators. |
| No `bias_rating` or `credibility_rating` on `DataSource` | Subjective editorial judgments. Inconsistent with political neutrality principle. Would require ongoing maintenance with no sourced basis. |
| Normalization inline in the asset (not a separate module) | Avoid premature abstraction. Rules are simple and few; extract to a shared module only when duplication justifies it. |
| `unitedstates/congress-legislators` for IDs only | Congress.gov is authoritative for member data. The unitedstates project is used exclusively for its ID cross-reference mapping, which Congress.gov does not expose in a single call. |
| `include_object` filter in Alembic | The `postgis/postgis` image installs extension tables (topology, TIGER geocoder) that Alembic's autogenerate would try to drop. Filter ensures only our own tables are managed. |
| Fixtures from live API calls | Pydantic models are validated against real responses, not invented payloads. This caught two real bugs: `birthYear` arriving as a string, and the `unitedstates.io` CDN being offline. |

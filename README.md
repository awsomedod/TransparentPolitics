# TransparentPolitics

A politically neutral, source-driven political intelligence platform aggregating federal and state legislative data, campaign finance, elections, news, and polling into an interactive web dashboard.

## Core principles

- Every displayed fact links to an official government source or named publication
- AI-generated content is clearly labeled and visually distinct from sourced facts
- All LLM inference is reproducible: model name, version, prompt version (git SHA), temperature, and seed are stored for every output
- Equal coverage of all parties; quarterly algorithmic bias audits

## Project structure

```
TransparentPolitics/
├── docs/           # Plan, ADRs, data source notes
├── backend/        # FastAPI + SQLAlchemy (Python)
├── frontend/       # Next.js 15 App Router (TypeScript)
├── etl/            # Dagster pipelines and data sources
├── ai/             # LLM inference pipeline (Phase 3)
├── prompts/        # Git-versioned prompt library (YAML)
└── infra/          # Docker Compose, Kubernetes configs
```

## Development phases

| Phase | Scope | Target |
|-------|-------|--------|
| 1 — Federal MVP | Congress profiles, voting records, FEC finance, news feed | Weeks 1–12 |
| 2 — Maps + States | Interactive map, state legislatures, elections, polling | Weeks 13–28 |
| 3 — AI Pipeline | Summarization, NER, deduplication, vote explanations | Weeks 29–44 |
| 4 — Advanced | Policy inference, comparison tools, developer API | Weeks 45+ |

## Full plan

See [`docs/plan.md`](docs/plan.md) for the complete technical product plan including architecture, data model, data sources, ETL strategy, AI pipeline design, legal considerations, and phased roadmap.

## Tech stack (summary)

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 · Dagster · Celery
- **Databases:** PostgreSQL 16 + PostGIS · OpenSearch 2 · Redis 7 · MinIO
- **Frontend:** Next.js 15 · MapLibre GL JS · Recharts · Tailwind · shadcn/ui
- **AI (Phase 3):** vLLM · Mistral Small 3.1 (Apache 2.0) · OLMo 3 (Apache 2.0) · Phi-4-mini (MIT) · spaCy · sentence-transformers · Langfuse
- **Infra:** Docker · Cloudflare CDN

## Data sources

Primary: CIV.IQ (MIT) · Congress.gov API · OpenFEC · OpenStates · Census TIGER/Line · MIT Election Lab · unitedstates/congress

All data sourced from official government APIs or open-licensed civic datasets. No proprietary data embedded in this repository.

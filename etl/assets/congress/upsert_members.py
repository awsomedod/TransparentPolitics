"""
Congress members upsert asset.

Reads raw member data from MinIO snapshots and upserts into PostgreSQL:
- parties, jurisdictions, offices, data_sources (reference tables)
- persons (keyed on bioguide_id)
- officeholders (current term for each member)

No normalization — values are stored exactly as Congress.gov returns them.
"""

import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset
from sqlalchemy import text
from sqlalchemy.engine import Engine

from resources import DatabaseResource, MinioSnapshotResource

# Party names → short abbreviations (derived, not normalized).
# Congress.gov doesn't provide abbreviations so we generate them.
_PARTY_SHORT: dict[str, str] = {
    "Democratic": "D",
    "Republican": "R",
    "Independent": "I",
    "Libertarian": "L",
    "Green": "G",
}


def _get_or_create_data_source(engine: Engine) -> uuid.UUID:
    """Ensure the Congress.gov data source row exists, return its ID."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM data_sources WHERE name = :name"),
            {"name": "Congress.gov API"},
        ).fetchone()
        if row:
            conn.execute(
                text("UPDATE data_sources SET last_fetched_at = :ts WHERE name = :name"),
                {"ts": datetime.now(UTC), "name": "Congress.gov API"},
            )
            return row[0]
        ds_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO data_sources
                    (id, name, url, type, license, attribution_text, fetch_frequency)
                VALUES (:id, :name, :url, :type, :license, :attribution, :freq)
            """),
            {
                "id": ds_id,
                "name": "Congress.gov API",
                "url": "https://api.congress.gov/v3/",
                "type": "api",
                "license": "US Government work, public domain",
                "attribution": "Data provided by the Library of Congress Congress.gov API",
                "freq": "nightly",
            },
        )
        return ds_id


def _get_or_create_jurisdiction(
    engine: Engine, name: str, j_type: str, parent_id: uuid.UUID | None = None
) -> uuid.UUID:
    """Ensure a jurisdiction row exists, return its ID."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM jurisdictions WHERE name = :name AND type = :type"),
            {"name": name, "type": j_type},
        ).fetchone()
        if row:
            return row[0]
        j_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO jurisdictions (id, name, type, parent_id)
                VALUES (:id, :name, :type, :parent_id)
            """),
            {"id": j_id, "name": name, "type": j_type, "parent_id": parent_id},
        )
        return j_id


def _get_or_create_party(engine: Engine, party_name: str) -> uuid.UUID:
    """Ensure a party row exists, return its ID."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM parties WHERE name = :name"),
            {"name": party_name},
        ).fetchone()
        if row:
            return row[0]
        short = _PARTY_SHORT.get(party_name, party_name[:3])
        # Handle short_name collision
        existing = conn.execute(
            text("SELECT id FROM parties WHERE short_name = :short"),
            {"short": short},
        ).fetchone()
        if existing:
            short = party_name[:5]
        p_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO parties (id, name, short_name)
                VALUES (:id, :name, :short_name)
            """),
            {"id": p_id, "name": party_name, "short_name": short},
        )
        return p_id


def _get_or_create_office(
    engine: Engine, title: str, chamber: str | None, jurisdiction_id: uuid.UUID
) -> uuid.UUID:
    """Ensure an office row exists, return its ID."""
    with engine.begin() as conn:
        if chamber:
            row = conn.execute(
                text(
                    "SELECT id FROM offices WHERE title = :title "
                    "AND chamber = :chamber AND jurisdiction_id = :jid"
                ),
                {"title": title, "chamber": chamber, "jid": jurisdiction_id},
            ).fetchone()
        else:
            row = conn.execute(
                text(
                    "SELECT id FROM offices WHERE title = :title "
                    "AND jurisdiction_id = :jid AND chamber IS NULL"
                ),
                {"title": title, "jid": jurisdiction_id},
            ).fetchone()
        if row:
            return row[0]
        o_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO offices (id, title, level, chamber, jurisdiction_id)
                VALUES (:id, :title, :level, :chamber, :jid)
            """),
            {
                "id": o_id,
                "title": title,
                "level": "federal",
                "chamber": chamber,
                "jid": jurisdiction_id,
            },
        )
        return o_id


def _upsert_person(engine: Engine, member: dict[str, Any]) -> uuid.UUID:
    """Upsert a person by bioguide_id, return the person's UUID."""
    bioguide_id = member["bioguide_id"]
    canonical_name = member.get("inverted_order_name") or member.get("bioguide_id")
    display_name = member.get("direct_order_name") or canonical_name

    birth_date = None
    if member.get("birth_year"):
        birth_date = date(member["birth_year"], 1, 1)
    death_date = None
    if member.get("death_year"):
        death_date = date(member["death_year"], 1, 1)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM persons WHERE bioguide_id = :bid"),
            {"bid": bioguide_id},
        ).fetchone()
        if row:
            conn.execute(
                text("""
                    UPDATE persons SET
                        canonical_name = :cname,
                        display_name = :dname,
                        birth_date = :bdate,
                        death_date = :ddate,
                        updated_at = :now
                    WHERE bioguide_id = :bid
                """),
                {
                    "cname": canonical_name,
                    "dname": display_name,
                    "bdate": birth_date,
                    "ddate": death_date,
                    "now": datetime.now(UTC),
                    "bid": bioguide_id,
                },
            )
            return row[0]
        p_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO persons
                    (id, canonical_name, display_name, birth_date,
                     death_date, bioguide_id)
                VALUES (:id, :cname, :dname, :bdate, :ddate, :bid)
            """),
            {
                "id": p_id,
                "cname": canonical_name,
                "dname": display_name,
                "bdate": birth_date,
                "ddate": death_date,
                "bid": bioguide_id,
            },
        )
        return p_id


def _upsert_officeholder(
    engine: Engine,
    person_id: uuid.UUID,
    office_id: uuid.UUID,
    party_id: uuid.UUID | None,
    jurisdiction_id: uuid.UUID | None,
    start_date: date | None,
    end_date: date | None,
    is_current: bool,
    data_source_id: uuid.UUID,
) -> None:
    """Upsert an officeholder record (keyed on person + office + start_date)."""
    with engine.begin() as conn:
        if start_date:
            row = conn.execute(
                text(
                    "SELECT id FROM officeholders "
                    "WHERE person_id = :pid AND office_id = :oid AND start_date = :sd"
                ),
                {"pid": person_id, "oid": office_id, "sd": start_date},
            ).fetchone()
        else:
            row = conn.execute(
                text(
                    "SELECT id FROM officeholders "
                    "WHERE person_id = :pid AND office_id = :oid "
                    "AND start_date IS NULL"
                ),
                {"pid": person_id, "oid": office_id},
            ).fetchone()

        if row:
            conn.execute(
                text("""
                    UPDATE officeholders SET
                        party_id = :party_id,
                        jurisdiction_id = :jid,
                        end_date = :end_date,
                        is_current = :is_current,
                        data_source_id = :dsid
                    WHERE id = :id
                """),
                {
                    "id": row[0],
                    "party_id": party_id,
                    "jid": jurisdiction_id,
                    "end_date": end_date,
                    "is_current": is_current,
                    "dsid": data_source_id,
                },
            )
        else:
            conn.execute(
                text("""
                    INSERT INTO officeholders
                        (id, person_id, office_id, party_id, jurisdiction_id,
                         start_date, end_date, is_current, data_source_id)
                    VALUES (:id, :pid, :oid, :party_id, :jid, :sd, :ed, :ic, :dsid)
                """),
                {
                    "id": uuid.uuid4(),
                    "pid": person_id,
                    "oid": office_id,
                    "party_id": party_id,
                    "jid": jurisdiction_id,
                    "sd": start_date,
                    "ed": end_date,
                    "ic": is_current,
                    "dsid": data_source_id,
                },
            )


def _log_ingest_error(
    engine: Engine,
    source: str,
    endpoint: str,
    error_message: str,
    raw_payload: str | None = None,
) -> None:
    """Write an error to the ingest_errors table."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ingest_errors (id, source, endpoint, error_message, raw_payload)
                VALUES (:id, :source, :endpoint, :msg, :payload)
            """),
            {
                "id": uuid.uuid4(),
                "source": source,
                "endpoint": endpoint,
                "msg": error_message,
                "payload": raw_payload,
            },
        )


@asset(
    group_name="congress",
    deps=["raw_congress_members"],
    description=(
        "Read Congress member snapshots from MinIO and upsert into PostgreSQL. "
        "Creates persons, parties, jurisdictions, offices, and officeholder records."
    ),
)
def congress_members(
    context: AssetExecutionContext,
    minio_snapshot: MinioSnapshotResource,
    database: DatabaseResource,
) -> MaterializeResult:
    """
    Reads the latest member_details_all.json snapshot from MinIO,
    maps to the DB schema, and upserts all records.
    """
    store = minio_snapshot.get_store()
    engine = database.get_engine()

    # Find the latest snapshot
    snapshots = store.list_snapshots(source="congress-gov")
    detail_snapshots = [s for s in snapshots if "member_details_all" in s]
    if not detail_snapshots:
        raise RuntimeError("No member_details_all snapshot found in MinIO")

    latest_snapshot = detail_snapshots[-1]  # sorted, last = most recent date
    context.log.info("Reading snapshot: %s", latest_snapshot)
    members: list[dict[str, Any]] = store.get_snapshot(latest_snapshot)
    context.log.info("Loaded %d member records from snapshot", len(members))

    # Set up reference data
    data_source_id = _get_or_create_data_source(engine)
    federal_jid = _get_or_create_jurisdiction(engine, "United States", "federal")

    # Caches to avoid repeated DB lookups
    party_cache: dict[str, uuid.UUID] = {}
    jurisdiction_cache: dict[str, uuid.UUID] = {"United States": federal_jid}
    office_cache: dict[str, uuid.UUID] = {}

    persons_upserted = 0
    officeholders_created = 0
    errors = 0

    for member in members:
        try:
            person_id = _upsert_person(engine, member)
            persons_upserted += 1

            # Process current term only (most recent by start_year)
            terms = member.get("terms", [])
            if not terms:
                continue

            current_term = max(terms, key=lambda t: t.get("start_year") or 0)
            member_type = current_term.get("member_type")
            chamber = current_term.get("chamber")
            state_name = current_term.get("state_name") or member.get("state")
            start_year = current_term.get("start_year")
            end_year = current_term.get("end_year")

            # Resolve party (from party_history, most recent)
            party_history = member.get("party_history", [])
            party_name = None
            if party_history:
                current_party = max(
                    party_history, key=lambda p: p.get("start_year") or 0
                )
                party_name = current_party.get("party_name")

            party_id = None
            if party_name:
                if party_name not in party_cache:
                    party_cache[party_name] = _get_or_create_party(engine, party_name)
                party_id = party_cache[party_name]

            # Resolve jurisdiction (state)
            state_jid = None
            if state_name:
                if state_name not in jurisdiction_cache:
                    jurisdiction_cache[state_name] = _get_or_create_jurisdiction(
                        engine, state_name, "state", parent_id=federal_jid
                    )
                state_jid = jurisdiction_cache[state_name]

            # Resolve office — use memberType as title, chamber directly from term
            office_title = member_type or "Unknown"
            office_key = f"{office_title}|{chamber}"
            if office_key not in office_cache:
                office_cache[office_key] = _get_or_create_office(
                    engine, office_title, chamber, federal_jid
                )
            office_id = office_cache[office_key]

            # Determine dates
            start_date = date(start_year, 1, 1) if start_year else None
            end_date = date(end_year, 1, 1) if end_year else None
            is_current = end_year is None

            _upsert_officeholder(
                engine,
                person_id=person_id,
                office_id=office_id,
                party_id=party_id,
                jurisdiction_id=state_jid,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current,
                data_source_id=data_source_id,
            )
            officeholders_created += 1

        except Exception as e:
            errors += 1
            context.log.warning(
                "Error processing member %s: %s",
                member.get("bioguide_id", "unknown"),
                str(e),
            )
            _log_ingest_error(
                engine,
                source="Congress.gov API",
                endpoint=f"/v3/member/{member.get('bioguide_id', 'unknown')}",
                error_message=str(e),
                raw_payload=json.dumps(member)[:2000],
            )

    context.log.info(
        "Upsert complete: %d persons, %d officeholders, %d errors",
        persons_upserted, officeholders_created, errors,
    )

    return MaterializeResult(
        metadata={
            "persons_upserted": MetadataValue.int(persons_upserted),
            "officeholders_created": MetadataValue.int(officeholders_created),
            "errors": MetadataValue.int(errors),
            "snapshot_used": MetadataValue.text(latest_snapshot),
        },
    )

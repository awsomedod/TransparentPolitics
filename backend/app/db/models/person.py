"""
Person tables: Person, PersonExternalId, Officeholder.
A Person is the canonical record for a politician or candidate.
Officeholder links a Person to an Office for a specific term.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.reference import DataSource, Jurisdiction, Office, Party


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date)
    death_date: Mapped[date | None] = mapped_column(Date)

    # Canonical cross-source identifiers. bioguide_id is the primary key for
    # federal legislators — unique and stable across Congress.gov, FEC, etc.
    bioguide_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    fec_candidate_id: Mapped[str | None] = mapped_column(String(20), index=True)
    openstates_id: Mapped[str | None] = mapped_column(String(50), index=True)
    wikidata_qid: Mapped[str | None] = mapped_column(String(30), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    external_ids: Mapped[list["PersonExternalId"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    officeholders: Mapped[list["Officeholder"]] = relationship(back_populates="person")


class PersonExternalId(Base):
    """Maps any external source ID (FEC, OpenStates, etc.) to a canonical Person."""

    __tablename__ = "person_external_ids"
    __table_args__ = (
        # One ID per source per person — prevents duplicate resolution writes.
        UniqueConstraint("person_id", "source_name", name="uq_person_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.id"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)

    person: Mapped[Person] = relationship(back_populates="external_ids")


class Officeholder(Base):
    """A person holding a specific office for a specific term."""

    __tablename__ = "officeholders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.id"), nullable=False, index=True
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offices.id"), nullable=False
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id"))
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jurisdictions.id")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(default=False, index=True)
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id")
    )

    person: Mapped[Person] = relationship(back_populates="officeholders")
    office: Mapped[Office] = relationship()
    party: Mapped[Party | None] = relationship()
    jurisdiction: Mapped[Jurisdiction | None] = relationship()
    data_source: Mapped[DataSource | None] = relationship()

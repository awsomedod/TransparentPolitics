"""
Reference / lookup tables: Party, Jurisdiction, Office, DataSource.
These have no foreign keys to other main tables and are seeded once at
migration time. All other models depend on these.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    short_name: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    color_hex: Mapped[str | None] = mapped_column(String(7))


class Jurisdiction(Base):
    """A political geography: federal, state, county, city, etc."""

    __tablename__ = "jurisdictions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # federal|state|county|city
    fips_code: Mapped[str | None] = mapped_column(String(10), index=True)
    # Self-referential: e.g. a state's parent is the federal jurisdiction
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jurisdictions.id"))


class Office(Base):
    """A type of elected office (e.g. US Senator, US Representative)."""

    __tablename__ = "offices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)   # federal|state|local
    chamber: Mapped[str | None] = mapped_column(String(50))          # house|senate|executive
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id"), nullable=False)


class DataSource(Base):
    """Registry of every upstream data source the ETL pipeline pulls from."""

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # api|bulk|rss|manual
    license: Mapped[str | None] = mapped_column(Text)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    bias_rating: Mapped[str | None] = mapped_column(String(50))
    credibility_rating: Mapped[str | None] = mapped_column(String(50))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_frequency: Mapped[str | None] = mapped_column(String(50))

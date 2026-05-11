"""
System / housekeeping tables used by the ETL pipeline.
These are written to by ingestors — never displayed directly to users.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestError(Base):
    """Records any record that failed validation or entity resolution during ingestion."""

    __tablename__ = "ingest_errors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

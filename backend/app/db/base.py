from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    All models in app/db/models/ inherit from this.
    Alembic reads Base.metadata to autogenerate migrations.
    """

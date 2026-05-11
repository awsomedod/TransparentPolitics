# Import all model modules here so every table is registered with
# Base.metadata before Alembic runs autogenerate.
from app.db.models import person, reference, system  # noqa: F401

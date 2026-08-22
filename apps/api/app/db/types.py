"""Portable JSON column type: native JSONB on PostgreSQL, JSON elsewhere (SQLite dev)."""

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

JSONType = JSON().with_variant(JSONB(), "postgresql")

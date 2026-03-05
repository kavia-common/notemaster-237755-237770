from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.models import Base


# PUBLIC_INTERFACE
async def init_db(engine: AsyncEngine) -> None:
    """Ensure required DB extension/tables/indexes exist (idempotent)."""
    # Extensions / indexes require raw SQL for IF NOT EXISTS and expression indexes.
    async with engine.begin() as conn:
        # pg_trgm for trigram indexes used by ILIKE search
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

        # Create tables from SQLAlchemy metadata (idempotent for missing tables).
        await conn.run_sync(Base.metadata.create_all)

        # Indexes aligned with notes_database/SCHEMA.md
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at DESC);")
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);"))

        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id);")
        )

        # Trigram indexes for fast substring search (lower(...) to normalize).
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_notes_title_trgm "
                "ON notes USING GIN (lower(title) gin_trgm_ops);"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_notes_content_trgm "
                "ON notes USING GIN (lower(content) gin_trgm_ops);"
            )
        )

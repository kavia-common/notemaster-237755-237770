from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, Table, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base SQLAlchemy declarative class."""


note_tags_table = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", BigInteger, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class Note(Base):
    """ORM model for notes table."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[List["Tag"]] = relationship(
        secondary=note_tags_table,
        back_populates="notes",
        lazy="selectin",
    )


class Tag(Base):
    """ORM model for tags table."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    notes: Mapped[List[Note]] = relationship(
        secondary=note_tags_table,
        back_populates="tags",
        lazy="selectin",
    )

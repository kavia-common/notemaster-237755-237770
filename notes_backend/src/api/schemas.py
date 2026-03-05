from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class NoteBase(BaseModel):
    title: str = Field(default="", max_length=2000, description="Note title.")
    content: str = Field(default="", max_length=200000, description="Note content.")
    tags: List[str] = Field(default_factory=list, description="List of tag names.")

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: List[str]) -> List[str]:
        """Normalize tags: trim, lowercase, drop empties, de-duplicate preserving order."""
        seen = set()
        out: List[str] = []
        for raw in v:
            t = (raw or "").strip()
            if not t:
                continue
            t = t.lower()
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out


class NoteCreate(NoteBase):
    """Payload to create a note."""


class NoteUpdate(BaseModel):
    """Payload to update a note; all fields optional for autosave-friendly PATCH."""

    title: Optional[str] = Field(default=None, max_length=2000, description="Updated title.")
    content: Optional[str] = Field(default=None, max_length=200000, description="Updated content.")
    tags: Optional[List[str]] = Field(default=None, description="Updated tag names list.")

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Reuse tag normalization for update payload."""
        if v is None:
            return None
        seen = set()
        out: List[str] = []
        for raw in v:
            t = (raw or "").strip()
            if not t:
                continue
            t = t.lower()
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out


class NoteOut(BaseModel):
    id: str = Field(..., description="Note id as string (frontend expects string).")
    title: str
    content: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime


class TagOut(BaseModel):
    name: str = Field(..., description="Tag name.")
    count: Optional[int] = Field(default=None, description="Number of notes using the tag.")


class PaginatedNotes(BaseModel):
    items: List[NoteOut] = Field(..., description="Returned notes.")
    page: int = Field(..., ge=1, description="1-based page number.")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page.")
    total: int = Field(..., ge=0, description="Total matching notes.")

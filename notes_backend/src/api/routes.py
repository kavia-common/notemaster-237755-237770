from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.db import get_db_session
from src.api.models import Note, Tag, note_tags_table
from src.api.schemas import NoteCreate, NoteOut, NoteUpdate, PaginatedNotes, TagOut


router = APIRouter(tags=["notes"])


def _note_to_out(note: Note) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        title=note.title,
        content=note.content,
        tags=[t.name for t in sorted(note.tags, key=lambda x: x.name)],
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _get_or_create_tags(session: AsyncSession, tag_names: List[str]) -> List[Tag]:
    if not tag_names:
        return []

    existing = (
        await session.execute(select(Tag).where(Tag.name.in_(tag_names)).order_by(Tag.name))
    ).scalars().all()
    existing_map = {t.name: t for t in existing}

    created: List[Tag] = []
    for name in tag_names:
        if name in existing_map:
            continue
        t = Tag(name=name)
        session.add(t)
        created.append(t)

    # Flush to assign ids for newly created tags before relationship assignment
    if created:
        await session.flush()

    # Return in the same order as normalized input
    return [existing_map.get(name) or next(t for t in created if t.name == name) for name in tag_names]


# PUBLIC_INTERFACE
@router.get(
    "/notes",
    response_model=List[NoteOut],
    summary="List/search notes",
    description="List notes ordered by updated_at desc. Supports optional substring search (q) and single tag filter (tag).",
    operation_id="list_notes",
)
async def list_notes(
    q: Optional[str] = Query(default=None, description="Substring search over title/content."),
    tag: Optional[str] = Query(default=None, description="Filter notes that have this tag name."),
    session: AsyncSession = Depends(get_db_session),
) -> List[NoteOut]:
    """List notes with optional q/tag filters (frontend uses this shape)."""
    stmt = select(Note).options(selectinload(Note.tags)).where(Note.is_archived.is_(False))

    if q:
        qn = q.strip().lower()
        if qn:
            like = f"%{qn}%"
            stmt = stmt.where(
                func.lower(Note.title).ilike(like) | func.lower(Note.content).ilike(like)
            )

    if tag:
        tn = tag.strip().lower()
        if tn:
            stmt = stmt.join(note_tags_table, note_tags_table.c.note_id == Note.id).join(
                Tag, Tag.id == note_tags_table.c.tag_id
            ).where(Tag.name == tn)

    stmt = stmt.order_by(Note.updated_at.desc(), Note.id.desc())
    notes = (await session.execute(stmt)).scalars().unique().all()
    return [_note_to_out(n) for n in notes]


# PUBLIC_INTERFACE
@router.get(
    "/notes/paginated",
    response_model=PaginatedNotes,
    summary="List/search notes (paginated)",
    description="Same as /notes but with pagination metadata for clients that prefer it.",
    operation_id="list_notes_paginated",
)
async def list_notes_paginated(
    q: Optional[str] = Query(default=None, description="Substring search over title/content."),
    tag: Optional[str] = Query(default=None, description="Filter notes that have this tag name."),
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedNotes:
    """Paginated note listing/search."""
    base = select(Note.id).where(Note.is_archived.is_(False))

    if q:
        qn = q.strip().lower()
        if qn:
            like = f"%{qn}%"
            base = base.where(
                func.lower(Note.title).ilike(like) | func.lower(Note.content).ilike(like)
            )

    if tag:
        tn = tag.strip().lower()
        if tn:
            base = base.join(note_tags_table, note_tags_table.c.note_id == Note.id).join(
                Tag, Tag.id == note_tags_table.c.tag_id
            ).where(Tag.name == tn)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    ids_stmt = (
        base.order_by(Note.updated_at.desc(), Note.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    ids = [r[0] for r in (await session.execute(ids_stmt)).all()]
    if not ids:
        return PaginatedNotes(items=[], page=page, page_size=page_size, total=total)

    notes_stmt = (
        select(Note)
        .options(selectinload(Note.tags))
        .where(Note.id.in_(ids))
        .order_by(Note.updated_at.desc(), Note.id.desc())
    )
    notes = (await session.execute(notes_stmt)).scalars().unique().all()
    return PaginatedNotes(items=[_note_to_out(n) for n in notes], page=page, page_size=page_size, total=total)


# PUBLIC_INTERFACE
@router.get(
    "/notes/{note_id}",
    response_model=NoteOut,
    summary="Get a note",
    operation_id="get_note",
)
async def get_note(note_id: str, session: AsyncSession = Depends(get_db_session)) -> NoteOut:
    """Fetch a single note by id."""
    try:
        nid = int(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid note id") from exc

    note = (
        await session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == nid)
        )
    ).scalar_one_or_none()
    if not note or note.is_archived:
        raise HTTPException(status_code=404, detail="Note not found")
    return _note_to_out(note)


# PUBLIC_INTERFACE
@router.post(
    "/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note",
    operation_id="create_note",
)
async def create_note(payload: NoteCreate, session: AsyncSession = Depends(get_db_session)) -> NoteOut:
    """Create a note and attach tags (tags auto-created by name)."""
    note = Note(title=payload.title, content=payload.content)
    session.add(note)
    await session.flush()  # assign note.id

    tags = await _get_or_create_tags(session, payload.tags)
    note.tags = tags

    await session.commit()
    await session.refresh(note)
    return _note_to_out(note)


# PUBLIC_INTERFACE
@router.patch(
    "/notes/{note_id}",
    response_model=NoteOut,
    summary="Update a note (autosave-friendly)",
    description="Partial update: only provided fields change. This is suitable for autosave (PATCH).",
    operation_id="update_note",
)
async def update_note(
    note_id: str, payload: NoteUpdate, session: AsyncSession = Depends(get_db_session)
) -> NoteOut:
    """Patch note fields; tags can be replaced if provided."""
    try:
        nid = int(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid note id") from exc

    note = (
        await session.execute(
            select(Note).options(selectinload(Note.tags)).where(Note.id == nid)
        )
    ).scalar_one_or_none()
    if not note or note.is_archived:
        raise HTTPException(status_code=404, detail="Note not found")

    changed = False
    if payload.title is not None:
        note.title = payload.title
        changed = True
    if payload.content is not None:
        note.content = payload.content
        changed = True
    if payload.tags is not None:
        tags = await _get_or_create_tags(session, payload.tags)
        note.tags = tags
        changed = True

    if not changed:
        # No-op patch should still return current note (useful for autosave debouncers)
        return _note_to_out(note)

    await session.commit()
    await session.refresh(note)
    return _note_to_out(note)


# PUBLIC_INTERFACE
@router.delete(
    "/notes/{note_id}",
    summary="Delete a note",
    operation_id="delete_note",
)
async def delete_note(note_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    """Hard-delete a note (join rows removed via ON DELETE CASCADE)."""
    try:
        nid = int(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid note id") from exc

    res = await session.execute(delete(Note).where(Note.id == nid))
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found")

    await session.commit()
    return {"ok": True}


tags_router = APIRouter(tags=["tags"])


# PUBLIC_INTERFACE
@tags_router.get(
    "/tags",
    response_model=List[TagOut],
    summary="List tags",
    description="List all tags with note usage counts.",
    operation_id="list_tags",
)
async def list_tags(session: AsyncSession = Depends(get_db_session)) -> List[TagOut]:
    """Return all tags with counts (for sidebar)."""
    stmt = (
        select(Tag.name, func.count(note_tags_table.c.note_id).label("count"))
        .select_from(Tag)
        .join(note_tags_table, note_tags_table.c.tag_id == Tag.id, isouter=True)
        .group_by(Tag.id)
        .order_by(Tag.name.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [TagOut(name=name, count=int(count or 0)) for name, count in rows]

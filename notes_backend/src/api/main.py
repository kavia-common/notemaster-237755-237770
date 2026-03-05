import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import get_engine
from src.api.routes import router as notes_router
from src.api.routes import tags_router
from src.api.schema_init import init_db


def _split_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


openapi_tags = [
    {"name": "health", "description": "Health and diagnostics."},
    {"name": "notes", "description": "CRUD/search for notes (autosave-friendly PATCH)."},
    {"name": "tags", "description": "Tag listing for filtering."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App lifespan: initialize DB schema/indexes at startup.

    This project uses a migrations-free, idempotent initializer aligned to the
    `notes_database/SCHEMA.md` documentation.
    """
    engine = get_engine()
    await init_db(engine)
    yield


app = FastAPI(
    title="NoteMaster API",
    description="Backend API for the NoteMaster notes app (notes, tags, search, autosave-friendly updates).",
    version="1.0.0",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)

# CORS notes:
# - Static-export Next.js apps will call the API from a browser origin, so CORS must allow that origin.
# - If you use allow_credentials=True, CORS cannot use wildcard "*" origins.
# Env vars supported:
# - ALLOWED_ORIGINS (csv), or FRONTEND_ORIGINS (csv), or FRONTEND_ORIGIN (single)
# - ALLOWED_METHODS/ALLOWED_HEADERS (csv)
frontend_origins_raw = (
    os.getenv("ALLOWED_ORIGINS")
    or os.getenv("FRONTEND_ORIGINS")
    or os.getenv("FRONTEND_ORIGIN")
    or "*"
)
allowed_origins = _split_csv(frontend_origins_raw)
allowed_headers = _split_csv(os.getenv("ALLOWED_HEADERS", "*"))
allowed_methods = _split_csv(os.getenv("ALLOWED_METHODS", "*"))
cors_max_age = int(os.getenv("CORS_MAX_AGE", "3600"))

# If we are allowing all origins, we must disable credentials.
# (Starlette/FastAPI will otherwise generate invalid CORS responses.)
allow_all_origins = allowed_origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else allowed_origins,
    allow_credentials=False if allow_all_origins else True,
    allow_methods=allowed_methods if allowed_methods != ["*"] else ["*"],
    allow_headers=allowed_headers if allowed_headers != ["*"] else ["*"],
    max_age=cors_max_age,
)


@app.get("/", tags=["health"], summary="Health check", operation_id="health_check")
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}


app.include_router(notes_router)
app.include_router(tags_router)

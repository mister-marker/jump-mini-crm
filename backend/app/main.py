"""FastAPI entry point: uvicorn app.main:app --app-dir backend."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from postgrest import APIError

from app.api import auth, leads, tags, webhooks
from app.api.deps import DatabaseDep
from app.core.config import get_settings
from app.core.supabase import create_supabase


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    db = await create_supabase(get_settings())
    application.state.supabase = db
    try:
        yield
    finally:
        await db.postgrest.aclose()
        await db.auth.close()
        await db.realtime.close()


app = FastAPI(title="Jump Ads CRM", version="0.1.0", lifespan=lifespan)
app.state.login_limiter = auth.LoginLimiter()
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (auth.router, leads.router, tags.router, webhooks.router):
    app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default errors may echo the entire body, including PIN/webhook secrets.
    errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(APIError)
async def database_error(request: Request, exc: APIError) -> JSONResponse:
    if exc.code == "23505":
        return JSONResponse({"detail": "This record already exists"}, status_code=409)
    if exc.code == "23503":
        return JSONResponse({"detail": "Related record does not exist"}, status_code=409)
    # Do not leak database details, request payloads or service keys.
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


@app.exception_handler(httpx.HTTPError)
async def upstream_error(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready(db: DatabaseDep) -> dict[str, str]:
    await db.table("users").select("id").limit(1).execute()
    return {"status": "ready"}

"""One async Supabase client per FastAPI lifespan, never a user session."""

from fastapi import Request
from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.core.config import Settings


async def create_supabase(settings: Settings) -> AsyncClient:
    return await acreate_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_service_role_key.get_secret_value(),
        options=AsyncClientOptions(auto_refresh_token=False, persist_session=False),
    )


def get_supabase(request: Request) -> AsyncClient:
    return request.app.state.supabase

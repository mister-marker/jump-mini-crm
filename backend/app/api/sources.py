"""Source directory: staff can read; only admins can add options."""

from fastapi import APIRouter

from app.api.deps import AdminUser, CurrentUser, DatabaseDep
from app.models.schemas import Source, SourceCreate

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("", response_model=list[Source])
async def list_sources(user: CurrentUser, db: DatabaseDep) -> list[Source]:
    result = await db.table("sources").select("id,name").order("name").execute()
    return [Source.model_validate(row) for row in result.data]


@router.post("", response_model=Source, status_code=201)
async def create_source(body: SourceCreate, user: AdminUser, db: DatabaseDep) -> Source:
    result = await db.table("sources").insert(body.model_dump()).execute()
    return Source.model_validate(result.data[0])

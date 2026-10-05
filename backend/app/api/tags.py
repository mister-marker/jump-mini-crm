from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DatabaseDep
from app.models.schemas import Tag, TagCreate

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=list[Tag])
async def list_tags(
    user: CurrentUser, db: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Tag]:
    result = await db.table("tags").select("*").order("name").range(
        offset, offset + limit - 1
    ).execute()
    return [Tag.model_validate(row) for row in result.data]


@router.post("", response_model=Tag, status_code=201)
async def create_tag(body: TagCreate, user: CurrentUser, db: DatabaseDep) -> Tag:
    result = await db.table("tags").insert(body.model_dump()).execute()
    return Tag.model_validate(result.data[0])

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import AdminUser, CurrentUser, DatabaseDep
from app.models.schemas import Lead, LeadCreate, LeadStatus, LeadUpdate
from app.services.leads import LEAD_SELECT, read_lead

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=list[Lead])
async def list_leads(
    user: CurrentUser, db: DatabaseDep,
    status: LeadStatus | None = None,
    tag_id: UUID | None = None,
    next_contact_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Lead]:
    # Keep all tags in the response while filtering parents through a separate embed.
    selection = LEAD_SELECT + (",filter_tags:lead_tags!inner(tag_id)" if tag_id else "")
    query = db.table("leads").select(selection)
    if status:
        query = query.eq("status", status)
    if tag_id:
        query = query.eq("filter_tags.tag_id", str(tag_id))
    if next_contact_date:
        query = query.eq("next_contact_date", next_contact_date.isoformat())
    result = await query.order("created_at", desc=True).order("id").range(
        offset, offset + limit - 1
    ).execute()
    return [Lead.model_validate({k: v for k, v in row.items() if k != "filter_tags"})
            for row in result.data]


@router.post("", response_model=Lead, status_code=201)
async def create_lead(body: LeadCreate, user: CurrentUser, db: DatabaseDep) -> Lead:
    result = await db.table("leads").insert(body.model_dump(mode="json")).execute()
    return Lead.model_validate(result.data[0])


@router.patch("/{lead_id}", response_model=Lead)
async def update_lead(
    lead_id: UUID, body: LeadUpdate, user: CurrentUser, db: DatabaseDep,
) -> Lead:
    result = await db.table("leads").update(
        body.model_dump(mode="json", exclude_unset=True)
    ).eq("id", str(lead_id)).execute()
    if not result.data:
        raise HTTPException(404, "Lead not found")
    return await read_lead(db, lead_id)


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: UUID, user: AdminUser, db: DatabaseDep) -> Response:
    result = await db.table("leads").delete().eq("id", str(lead_id)).execute()
    if not result.data:
        raise HTTPException(404, "Lead not found")
    return Response(status_code=204)


@router.post("/{lead_id}/tags/{tag_id}", response_model=Lead)
async def assign_tag(
    lead_id: UUID, tag_id: UUID, user: CurrentUser, db: DatabaseDep,
) -> Lead:
    await read_lead(db, lead_id)
    tag = await db.table("tags").select("id").eq("id", str(tag_id)).limit(1).execute()
    if not tag.data:
        raise HTTPException(404, "Tag not found")
    await db.table("lead_tags").upsert(
        {"lead_id": str(lead_id), "tag_id": str(tag_id)},
        on_conflict="lead_id,tag_id", ignore_duplicates=True,
    ).execute()
    return await read_lead(db, lead_id)


@router.delete("/{lead_id}/tags/{tag_id}", response_model=Lead)
async def remove_tag(lead_id: UUID, tag_id: UUID, user: CurrentUser, db: DatabaseDep) -> Lead:
    await read_lead(db, lead_id)
    await db.table("lead_tags").delete().eq("lead_id", str(lead_id)).eq("tag_id", str(tag_id)).execute()
    return await read_lead(db, lead_id)

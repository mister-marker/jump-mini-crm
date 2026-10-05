from uuid import UUID

from fastapi import HTTPException
from supabase import AsyncClient

from app.models.schemas import Lead, LeadCreate

LEAD_SELECT = "*,tags(*)"


async def create_bot_lead(db: AsyncClient, submission_id: UUID, lead: LeadCreate) -> UUID:
    """Persist the lead and tag atomically; retries use the same submission ID."""
    result = await db.rpc("create_bot_lead", {
        "p_id": str(submission_id), "p_name": lead.name,
        "p_contact": lead.contact, "p_request": lead.request,
    }).execute()
    return UUID(result.data)


async def read_lead(db: AsyncClient, lead_id: UUID) -> Lead:
    result = await db.table("leads").select(LEAD_SELECT).eq("id", str(lead_id)).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Lead not found")
    return Lead.model_validate(result.data[0])

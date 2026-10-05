from uuid import UUID

from fastapi import HTTPException
from supabase import AsyncClient

from app.models.schemas import Lead

LEAD_SELECT = "*,tags(*)"


async def read_lead(db: AsyncClient, lead_id: UUID) -> Lead:
    result = await db.table("leads").select(LEAD_SELECT).eq("id", str(lead_id)).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Lead not found")
    return Lead.model_validate(result.data[0])

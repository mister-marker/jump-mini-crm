import hmac

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.deps import DatabaseDep, SettingsDep
from app.models.schemas import ExternalLead, WebhookResult
from app.services.webhook_filter import is_spam

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


@router.post("/external", response_model=WebhookResult, status_code=201)
async def external_webhook(
    body: ExternalLead, settings: SettingsDep, db: DatabaseDep,
) -> WebhookResult | JSONResponse:
    if body.secret is None or not hmac.compare_digest(
        body.secret.get_secret_value().encode(), settings.webhook_secret.get_secret_value().encode()
    ):
        raise HTTPException(401, "Invalid webhook credentials")
    if is_spam(body.request):
        return JSONResponse({"error": "Request filtered as spam"}, status_code=400)
    # One database transaction creates the lead and its automatic tags together.
    result = await db.rpc("create_webhook_lead", {
        "p_name": body.name, "p_contact": body.contact, "p_request": body.request,
    }).execute()
    return WebhookResult(lead_id=result.data)

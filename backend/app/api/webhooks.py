import hmac
import logging

from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.deps import DatabaseDep, SettingsDep
from app.models.schemas import ExternalLead, WebhookResult
from app.services.webhook_filter import is_spam

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/telegram")
async def telegram_webhook(request: Request, settings: SettingsDep) -> dict[str, bool]:
    secret = settings.telegram_webhook_secret
    if secret is None:
        raise HTTPException(503, "Telegram webhook is not configured")
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied.encode(), secret.get_secret_value().encode()):
        raise HTTPException(401, "Invalid webhook credentials")
    runtime = request.app.state.telegram
    if runtime is None:
        raise HTTPException(503, "Telegram webhook is not configured")
    try:
        update = Update.model_validate(await request.json(), context={"bot": runtime.bot})
    except (ValueError, ValidationError):
        raise HTTPException(400, "Invalid Telegram update") from None
    try:
        await runtime.process(update)
    except Exception as exc:
        # Telegram retries non-2xx responses. Never log tokens, contact data or SDK URLs.
        logger.warning("Telegram update %s failed (%s)", update.update_id, type(exc).__name__)
        raise HTTPException(503, "Unable to process Telegram update; retry later") from None
    return {"ok": True}


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

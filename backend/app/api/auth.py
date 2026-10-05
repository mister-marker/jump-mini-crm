import hmac
from collections import OrderedDict
from time import monotonic

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import DatabaseDep, SettingsDep
from app.core.security import create_access_token, unauthorized, validate_init_data
from app.models.schemas import PinLogin, TelegramLogin, TokenResponse, User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginLimiter:
    """Bounded per-process limiter. Run one worker; add gateway limits when scaling."""

    def __init__(self) -> None:
        self.attempts: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def check(self, key: str) -> None:
        now = monotonic()
        start, count = self.attempts.get(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        if count >= 10:
            raise HTTPException(429, "Too many login attempts", headers={"Retry-After": "60"})
        self.attempts[key] = (start, count + 1)
        self.attempts.move_to_end(key)
        if len(self.attempts) > 10000:
            self.attempts.popitem(last=False)


def check_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    request.app.state.login_limiter.check(host)


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(
    body: TelegramLogin, request: Request, response: Response,
    db: DatabaseDep, settings: SettingsDep,
) -> TokenResponse:
    check_rate_limit(request)
    telegram_id = validate_init_data(body.init_data, settings)
    result = await db.table("users").select("*").eq("telegram_id", telegram_id).limit(1).execute()
    if not result.data:
        raise HTTPException(403, "This Telegram account has no CRM access")
    user = User.model_validate(result.data[0])
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=create_access_token(user, settings, method="telegram"),
        expires_in=settings.jwt_ttl_seconds,
    )


@router.post("/pin", response_model=TokenResponse)
async def pin_login(
    body: PinLogin, request: Request, response: Response,
    db: DatabaseDep, settings: SettingsDep,
) -> TokenResponse:
    check_rate_limit(request)
    if not settings.pin_login_enabled:
        raise HTTPException(403, "Demo login is disabled")
    expected_pin = settings.browser_pin.get_secret_value().encode()
    if not hmac.compare_digest(body.pin.encode(), expected_pin):
        raise unauthorized()
    result = await db.table("users").select("*").eq(
        "id", str(settings.demo_manager_id)
    ).limit(1).execute()
    if not result.data or result.data[0]["role"] != "manager":
        raise HTTPException(503, "Demo manager is not configured; apply the migration")
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=create_access_token(
            User.model_validate(result.data[0]), settings, method="pin"
        ),
        expires_in=settings.jwt_ttl_seconds,
    )

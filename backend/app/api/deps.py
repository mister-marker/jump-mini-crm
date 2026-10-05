from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token, unauthorized
from app.core.supabase import get_supabase
from app.models.schemas import User

SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[AsyncClient, Depends(get_supabase)]
bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: SettingsDep,
    db: DatabaseDep,
) -> User:
    if credentials is None:
        raise unauthorized()
    claims = decode_access_token(credentials.credentials, settings)
    result = await db.table("users").select("*").eq("id", claims["sub"]).limit(1).execute()
    if not result.data:
        raise unauthorized()
    user = User.model_validate(result.data[0])
    # Read permissions from the database on every request, so demotion is immediate.
    if claims["amr"] == "pin":
        if not settings.pin_login_enabled or user.id != settings.demo_manager_id:
            raise unauthorized()
        user = user.model_copy(update={"role": "manager"})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]

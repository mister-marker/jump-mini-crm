"""Telegram HMAC and application JWT verification."""

import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt

from app.core.config import Settings
from app.models.schemas import User


def unauthorized() -> HTTPException:
    return HTTPException(
        401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"}
    )


def validate_init_data(raw: str, settings: Settings) -> int:
    """Verify the exact decoded fields before trusting the Telegram user ID."""
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError("Duplicate fields")
        received_hash = data.pop("hash")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", received_hash):
            raise ValueError("Invalid hash")
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret = hmac.new(
            b"WebAppData", settings.telegram_bot_token.get_secret_value().encode(), hashlib.sha256
        ).digest()
        expected_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash.lower()):
            raise ValueError("Invalid signature")
        auth_date = int(data["auth_date"])
        now = int(time.time())
        if not now - settings.telegram_auth_max_age_seconds <= auth_date <= (
            now + settings.telegram_clock_skew_seconds
        ):
            raise ValueError("Expired or future auth_date")
        user = json.loads(data["user"])
        telegram_id = user["id"]
        if type(telegram_id) is not int or not 0 < telegram_id <= 2**63 - 1:
            raise ValueError("Invalid Telegram ID")
        return telegram_id
    except (ValueError, KeyError, TypeError) as exc:
        raise unauthorized() from exc


def create_access_token(user: User, settings: Settings, *, method: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user.id), "iat": now, "nbf": now,
            "exp": now + settings.jwt_ttl_seconds,
            "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
            "type": "access", "amr": method,
        },
        settings.jwt_secret.get_secret_value(), algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
            audience=settings.jwt_audience, issuer=settings.jwt_issuer,
            options={
                "require_sub": True, "require_exp": True, "require_iat": True,
                "require_nbf": True, "require_iss": True, "require_aud": True,
            },
        )
        UUID(claims["sub"])
        if claims.get("type") != "access" or claims.get("amr") not in ("pin", "telegram"):
            raise ValueError("Invalid token type")
        # python-jose validates iat's format but does not reject future issue dates.
        if any(type(claims[name]) is not int for name in ("iat", "nbf", "exp")):
            raise ValueError("Invalid token timestamps")
        now = int(time.time())
        if claims["iat"] > now or claims["exp"] <= now:
            raise ValueError("Invalid token lifetime")
        return claims
    except (JWTError, ValueError, TypeError, KeyError) as exc:
        raise unauthorized() from exc

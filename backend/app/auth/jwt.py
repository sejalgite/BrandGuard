"""
app/auth/jwt.py
JWT creation and decoding using python-jose with HS256.
Enforces algorithm restriction and embeds unique jti claim for revocation tracking.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token.

    *data* should contain at minimum:
      - "sub"  : str(user_id)
      - "org"  : str(organization_id)
      - "role" : role name string

    The token embeds an ``exp`` claim and a unique ``jti`` (JWT ID).
    """
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    if "jti" not in to_encode:
        to_encode["jti"] = uuid.uuid4().hex

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Restricts allowed signing algorithm strictly to settings.ALGORITHM (HS256).

    Raises:
        jose.JWTError: if the token signature is invalid, expired, or claims are malformed.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_signature": True, "verify_exp": True},
    )


__all__ = ["create_access_token", "decode_token", "JWTError"]

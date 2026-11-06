"""
app/auth/dependencies.py
FastAPI dependency functions for JWT authentication, tenant isolation, token revocation,
and automatic CSRF validation for cookie-authenticated requests.
"""
import uuid
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.auth.csrf import verify_csrf
from app.database import get_db
from app.models.user import User
from app.models.token import RevokedToken

# auto_error=False allows falling back to cookies
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def extract_token_from_request(
    request: Request,
    header_token: Optional[str] = Depends(oauth2_scheme),
) -> str:
    """
    Extract token from Authorization header (Bearer) or from HttpOnly cookie.
    If authenticated via cookie on state-changing requests, verifies CSRF token.
    Provides defense-in-depth against both XSS and CSRF while supporting both browser and API callers.
    """
    if header_token:
        # Bearer token authentication: immune to browser ambient cookie CSRF
        return header_token

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        # State-changing requests using cookie authentication must pass CSRF validation
        verify_csrf(request)
        return cookie_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(extract_token_from_request),
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the JWT, check revocation, extract user_id and org_id, then load the User row.

    Security controls:
    1. Algorithm restriction to HS256.
    2. Revocation check against PostgreSQL revoked_tokens table.
    3. Composite tenant filter: User.id == sub AND User.organization_id == org.
    4. Active role loaded directly from PostgreSQL (prevents stale token claims).
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        user_id_str: str | None = payload.get("sub")
        org_id_str: str | None = payload.get("org")
        jti: str | None = payload.get("jti")

        if user_id_str is None or org_id_str is None:
            raise credentials_exc

        user_id = uuid.UUID(user_id_str)
        org_id = uuid.UUID(org_id_str)
    except (JWTError, ValueError):
        raise credentials_exc

    # Check if token was revoked via logout or administrative action
    if jti:
        is_revoked = (
            db.query(RevokedToken)
            .filter(RevokedToken.token_jti == jti)
            .first()
        )
        if is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Composite query enforces multi-tenant isolation at database level
    user: User | None = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == org_id)
        .first()
    )
    if user is None:
        raise credentials_exc

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Raise HTTP 403 if the account has been deactivated."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )
    return current_user

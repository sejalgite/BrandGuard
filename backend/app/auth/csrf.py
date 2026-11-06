"""
app/auth/csrf.py
Cross-Site Request Forgery (CSRF) protection using a signed double-submit cookie pattern.

Rules:
- State-changing HTTP methods (POST, PUT, PATCH, DELETE) authenticated via ambient cookies
  require a matching X-CSRF-Token request header.
- Requests authenticated explicitly via `Authorization: Bearer <token>` are immune to CSRF
  and do not require CSRF tokens.
- Public authentication bootstrap and login endpoints are exempt from token validation,
  but set a fresh CSRF cookie for the client.
"""
import hmac
import secrets
from fastapi import HTTPException, Request, Response, status

from app.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def generate_csrf_token() -> str:
    """Generate a high-entropy cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """
    Set the client-readable CSRF cookie.
    Must be readable by frontend JavaScript (httponly=False) to read and attach to headers.
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def verify_csrf(request: Request) -> None:
    """
    Validate CSRF token for state-changing requests authenticated through cookies.
    Raises HTTP 403 Forbidden on missing or mismatched CSRF tokens.
    """
    # Safe methods do not modify state
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return

    # If the caller provides an explicit Bearer token header, CSRF protection is not needed
    # because browsers never automatically attach Bearer headers across origins.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return

    # Check if this request is relying on an ambient session cookie
    access_cookie = request.cookies.get("access_token")
    if not access_cookie:
        # Not authenticated via cookie; let authentication dependency handle 401
        return

    # Request is authenticated via cookie: CSRF token is mandatory
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")

    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing for cookie-authenticated request.",
        )

    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch.",
        )


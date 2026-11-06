"""
app/api/v1/auth.py
Authentication, organisation bootstrap, and session management API endpoints.
Implements:
- Atomic organisation bootstrap with initial Admin creation and rate-limiting abuse protection.
- Public registration restricted strictly to non-privileged roles (CONTENT_CREATOR).
- In-memory rate limiting against brute-force login attempts with 429 response.
- Argon2 password verification with timing-attack mitigation.
- Failed login audit logging for security monitoring.
- Server-side JWT revocation via PostgreSQL denylist on logout.
- Defense-in-depth HttpOnly cookie transport combined with Bearer token support.
- CSRF token emission and double-submit validation for cookie sessions.
- Environment-aware cookie security (Secure=True in production, False in local HTTP).
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.token import RevokedToken
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token, decode_token
from app.auth.dependencies import get_current_active_user, extract_token_from_request
from app.auth.rbac import ROLE_PERMISSIONS
from app.auth.csrf import generate_csrf_token, set_csrf_cookie, CSRF_COOKIE_NAME
from app.auth.rate_limiter import limiter
from app.audit.audit_logger import log_action
from app.schemas.auth import (
    OrganizationBootstrap,
    OrganizationCreate,
    OrganizationOut,
    UserRegister,
    UserOut,
    LoginRequest,
    TokenResponse,
    MessageResponse,
)

logger = logging.getLogger("brandguard.auth")
router = APIRouter()


def _user_to_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    perms = ROLE_PERMISSIONS.get(user.role, set())
    out.permissions = sorted(list(perms))
    return out


def _get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# CSRF Token Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/csrf",
    summary="Fetch or refresh a CSRF token for cookie-based authentication",
)
def get_csrf_token(response: Response):
    token = generate_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


# ---------------------------------------------------------------------------
# Organisation Bootstrap (One-time atomic bootstrap with first Admin)
# ---------------------------------------------------------------------------

@router.post(
    "/bootstrap",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="One-time atomic organisation bootstrap with initial Admin creation",
)
def bootstrap_organization(
    payload: OrganizationBootstrap,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Controlled, atomic bootstrap process:
    Creates a new organisation and its initial Admin account in a single transaction.
    Prevents repeated or concurrent bootstrap requests from creating unauthorized Admin accounts.
    Protected by IP rate limiting against automated abuse.
    """
    client_ip = _get_client_ip(request)
    limiter.check_bootstrap_rate_limit(client_ip)
    limiter.record_bootstrap_attempt(client_ip)

    existing_org = (
        db.query(Organization)
        .filter(Organization.slug == payload.org_slug)
        .first()
    )
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organisation with slug '{payload.org_slug}' already exists. Bootstrap cannot be repeated.",
        )

    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    new_org = Organization(
        id=org_id,
        name=payload.org_name,
        slug=payload.org_slug,
    )
    db.add(new_org)

    admin_user = User(
        id=admin_id,
        organization_id=org_id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_full_name,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin_user)

    try:
        db.flush()
        # Audit trail for organisation bootstrap and initial admin provisioning
        log_action(
            db,
            organization_id=org_id,
            actor_id=admin_id,
            action="ORGANIZATION_BOOTSTRAPPED",
            target_entity="ORGANIZATION",
            target_id=org_id,
            details={"org_name": payload.org_name, "slug": payload.org_slug},
        )
        log_action(
            db,
            organization_id=org_id,
            actor_id=admin_id,
            action="USER_REGISTERED",
            target_entity="USER",
            target_id=admin_id,
            details={"email": payload.admin_email, "role": "ADMIN", "is_bootstrap": True},
        )
        db.commit()
        db.refresh(admin_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organisation slug or Admin email conflict during bootstrap.",
        )

    # Issue JWT token
    token = create_access_token({
        "sub": str(admin_user.id),
        "org": str(admin_user.organization_id),
        "role": admin_user.role.value,
    })

    # Set HttpOnly cookie for browser security (Secure=True in production)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # Issue CSRF double-submit cookie
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)

    logger.info("Organisation bootstrapped: %s (slug=%s, admin=%s)", new_org.name, new_org.slug, admin_user.email)
    return TokenResponse(access_token=token, user=_user_to_out(admin_user))


# ---------------------------------------------------------------------------
# Organisation Discovery & Lookup
# ---------------------------------------------------------------------------

@router.get(
    "/organizations",
    response_model=List[OrganizationOut],
    summary="List organisations",
)
def list_organizations(db: Session = Depends(get_db)):
    return db.query(Organization).order_by(Organization.name.asc()).all()


# ---------------------------------------------------------------------------
# Public User Registration (Restricted strictly to CONTENT_CREATOR)
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Public user registration within an existing organisation",
)
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Public registration endpoint.
    Users cannot self-assign privileged roles (ADMIN, BRAND_MANAGER, REVIEWER, etc.).
    Any attempt to request a privileged role is rejected with HTTP 403 Forbidden.
    """
    if payload.role is not None and payload.role != UserRole.CONTENT_CREATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration cannot self-assign privileged roles. Privileged accounts must be provisioned by an Admin.",
        )

    # Resolve target organisation
    org = None
    if payload.organization_id:
        org = db.query(Organization).filter(Organization.id == payload.organization_id).first()
    elif payload.organization_slug:
        org = db.query(Organization).filter(Organization.slug == payload.organization_slug).first()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found.",
        )

    org_id = org.id

    # Check e-mail uniqueness within organisation
    duplicate = (
        db.query(User)
        .filter(
            User.organization_id == org_id,
            User.email == payload.email,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this e-mail already exists in the organisation.",
        )

    new_user = User(
        id=uuid.uuid4(),
        organization_id=org_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.CONTENT_CREATOR,  # Enforce non-privileged role
        is_active=True,
    )
    db.add(new_user)

    try:
        db.flush()
        log_action(
            db,
            organization_id=org_id,
            actor_id=new_user.id,
            action="USER_REGISTERED",
            target_entity="USER",
            target_id=new_user.id,
            details={"email": payload.email, "role": "CONTENT_CREATOR"},
        )
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this e-mail already exists in the organisation.",
        )

    logger.info("User registered: %s (org=%s)", new_user.email, org_id)
    return _user_to_out(new_user)


# ---------------------------------------------------------------------------
# Login with Brute-Force Rate Limiting
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with e-mail, password and organisation ID or slug",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    client_ip = _get_client_ip(request)

    # Enforce brute-force rate limiting: raises HTTP 429 if threshold exceeded
    limiter.check_login_rate_limit(client_ip, payload.email)

    # Resolve organisation
    org = None
    if payload.organization_id:
        org = db.query(Organization).filter(Organization.id == payload.organization_id).first()
    elif payload.organization_slug:
        org = db.query(Organization).filter(Organization.slug == payload.organization_slug).first()

    if org is None:
        limiter.record_login_failure(client_ip, payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org_id = org.id

    # Query user row
    user: User | None = (
        db.query(User)
        .filter(
            User.organization_id == org_id,
            User.email == payload.email,
        )
        .first()
    )

    # Constant-time failure path
    dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$AAAA$AAAA"
    candidate_hash = user.hashed_password if user else dummy_hash

    if not verify_password(payload.password, candidate_hash) or user is None:
        limiter.record_login_failure(client_ip, payload.email)

        # Audit failed login attempt for security monitoring
        try:
            log_action(
                db,
                organization_id=org_id,
                actor_id=None,
                action="USER_LOGIN_FAILED",
                target_entity="USER",
                target_id=user.id if user else uuid.UUID(int=0),
                details={"attempted_email": payload.email, "ip": client_ip},
            )
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Successful authentication: clear failure count
    limiter.record_login_success(client_ip, payload.email)

    token = create_access_token({
        "sub": str(user.id),
        "org": str(user.organization_id),
        "role": user.role.value,
    })

    log_action(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="USER_LOGIN",
        target_entity="USER",
        target_id=user.id,
    )
    db.commit()

    # Set HttpOnly session cookie (Secure=True in production)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # Set client-accessible CSRF cookie
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)

    logger.info("User logged in: %s (org=%s)", user.email, user.organization_id)
    return TokenResponse(access_token=token, user=_user_to_out(user))


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the authenticated user's profile with active permissions",
)
def get_me(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


# ---------------------------------------------------------------------------
# Logout (Server-side Token Revocation & Cookie Cleanup)
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and invalidate access token in PostgreSQL denylist",
)
def logout(
    response: Response,
    token: str = Depends(extract_token_from_request),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Genuine token/session revocation:
    Extracts the unique jti and expiry from the presented JWT and stores it in
    the revoked_tokens table. Subsequent requests presenting this token are
    immediately rejected by authentication dependencies with HTTP 401.
    """
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        exp_timestamp = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            if exp_timestamp
            else datetime.now(tz=timezone.utc)
        )
    except Exception:
        jti = None
        expires_at = datetime.now(tz=timezone.utc)

    if jti:
        revocation = RevokedToken(
            id=uuid.uuid4(),
            organization_id=current_user.organization_id,
            token_jti=jti,
            user_id=current_user.id,
            expires_at=expires_at,
        )
        db.add(revocation)

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="USER_LOGOUT",
        target_entity="USER",
        target_id=current_user.id,
    )
    db.commit()

    # Clear HttpOnly auth cookie
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
    )

    # Clear CSRF cookie
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        httponly=False,
        samesite="lax",
    )

    logger.info("User logged out and token revoked: %s (jti=%s)", current_user.email, jti)
    return MessageResponse(message="Logged out successfully. Token revoked.")

"""
app/api/v1/users.py
User management, role assignment, and role/permission verification endpoints.
Enforces organization scoping on all queries and operations.
"""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.auth.password import hash_password
from app.auth.dependencies import get_current_active_user
from app.auth.rbac import (
    require_permission,
    require_role,
    ROLE_PERMISSIONS,
    PERM_MANAGE_USERS,
    PERM_UPLOAD_DOCS,
    PERM_VIEW_AUDIT_LOGS,
    PERM_ACCESS_AGENCY_PORTAL,
    PERM_VIEW_ANALYTICS,
    PERM_APPROVE_LEGAL,
)
from app.schemas.auth import (
    UserOut,
    UserCreateAdmin,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.audit.audit_logger import log_action

router = APIRouter()


def _user_to_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    perms = ROLE_PERMISSIONS.get(user.role, set())
    out.permissions = sorted(list(perms))
    return out


# ---------------------------------------------------------------------------
# Current User
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the authenticated user's profile",
)
def users_me(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


# ---------------------------------------------------------------------------
# Admin User Management
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin-only user creation with role assignment (tenant-scoped)",
    dependencies=[Depends(require_permission(PERM_MANAGE_USERS))],
)
def admin_create_user(
    payload: UserCreateAdmin,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Authorized Admin provisions a new user with a specific role within their organisation.
    """
    duplicate = (
        db.query(User)
        .filter(
            User.organization_id == current_user.organization_id,
            User.email == payload.email,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this e-mail already exists in your organisation.",
        )

    new_user = User(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="USER_PROVISIONED_BY_ADMIN",
        target_entity="USER",
        target_id=new_user.id,
        details={"email": payload.email, "role": payload.role.value},
    )
    db.commit()
    db.refresh(new_user)
    return _user_to_out(new_user)


@router.get(
    "",
    response_model=List[UserOut],
    summary="List users within the caller's organisation only (tenant-isolated)",
)
def list_org_users(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Returns only users belonging to the authenticated user's organisation.
    Cross-tenant records are never exposed.
    """
    users = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [_user_to_out(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get user details by ID within caller's organisation",
)
def get_user_by_id(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Returns a user only if they belong to the caller's organisation.
    Attempts to read across tenant boundaries return 404.
    """
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your organisation.",
        )
    return _user_to_out(user)


@router.patch(
    "/{user_id}/role",
    response_model=UserOut,
    summary="Change user role (Admin only, tenant-scoped)",
    dependencies=[Depends(require_permission(PERM_MANAGE_USERS))],
)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Authorized Admin modifies a user's role.
    Changes take effect immediately because role permissions are loaded from the database on every request.
    """
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your organisation.",
        )

    old_role = user.role.value
    user.role = payload.role

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="USER_ROLE_CHANGED",
        target_entity="USER",
        target_id=user.id,
        details={"old_role": old_role, "new_role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return _user_to_out(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserOut,
    summary="Activate or deactivate a user (Admin only, tenant-scoped)",
    dependencies=[Depends(require_permission(PERM_MANAGE_USERS))],
)
def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your organisation.",
        )

    user.is_active = payload.is_active
    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="USER_STATUS_UPDATED",
        target_entity="USER",
        target_id=user.id,
        details={"is_active": payload.is_active},
    )
    db.commit()
    db.refresh(user)
    return _user_to_out(user)


# ---------------------------------------------------------------------------
# RBAC verification probe endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/rbac/admin-check",
    response_model=UserOut,
    summary="Requires manage_users permission (Admin only)",
    dependencies=[Depends(require_permission(PERM_MANAGE_USERS))],
)
def rbac_admin_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


@router.get(
    "/rbac/upload-check",
    response_model=UserOut,
    summary="Requires upload_docs permission",
    dependencies=[Depends(require_permission(PERM_UPLOAD_DOCS))],
)
def rbac_upload_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


@router.get(
    "/rbac/audit-check",
    response_model=UserOut,
    summary="Requires view_audit_logs permission",
    dependencies=[Depends(require_permission(PERM_VIEW_AUDIT_LOGS))],
)
def rbac_audit_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


@router.get(
    "/rbac/agency-check",
    response_model=UserOut,
    summary="Requires access_agency_portal permission",
    dependencies=[Depends(require_permission(PERM_ACCESS_AGENCY_PORTAL))],
)
def rbac_agency_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


@router.get(
    "/rbac/legal-check",
    response_model=UserOut,
    summary="Requires approve_legal permission",
    dependencies=[Depends(require_permission(PERM_APPROVE_LEGAL))],
)
def rbac_legal_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)


@router.get(
    "/rbac/analytics-check",
    response_model=UserOut,
    summary="Requires view_analytics permission",
    dependencies=[Depends(require_permission(PERM_VIEW_ANALYTICS))],
)
def rbac_analytics_check(current_user: User = Depends(get_current_active_user)):
    return _user_to_out(current_user)

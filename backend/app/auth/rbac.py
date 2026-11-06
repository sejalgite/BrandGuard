"""
app/auth/rbac.py
Role-based permission matrix and FastAPI dependency factories.
"""
from typing import Set
from fastapi import Depends, HTTPException, status

from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Permission strings (canonical names, used throughout the application)
# ---------------------------------------------------------------------------
PERM_READ_OWN_DOCS       = "read_own_docs"
PERM_UPLOAD_DOCS         = "upload_docs"
PERM_RUN_ANALYSIS        = "run_analysis"
PERM_MANAGE_CONSTITUTION = "manage_constitution"
PERM_APPROVE_FINDINGS    = "approve_findings"
PERM_APPROVE_LEGAL       = "approve_legal"
PERM_APPROVE_DOCS        = "approve_docs"
PERM_VIEW_ANALYTICS      = "view_analytics"
PERM_MANAGE_USERS        = "manage_users"
PERM_VIEW_AUDIT_LOGS     = "view_audit_logs"
PERM_ASSIGN_REVIEWERS    = "assign_reviewers"
PERM_ACCESS_AGENCY_PORTAL = "access_agency_portal"

ALL_PERMISSIONS: Set[str] = {
    PERM_READ_OWN_DOCS,
    PERM_UPLOAD_DOCS,
    PERM_RUN_ANALYSIS,
    PERM_MANAGE_CONSTITUTION,
    PERM_APPROVE_FINDINGS,
    PERM_APPROVE_LEGAL,
    PERM_APPROVE_DOCS,
    PERM_VIEW_ANALYTICS,
    PERM_MANAGE_USERS,
    PERM_VIEW_AUDIT_LOGS,
    PERM_ASSIGN_REVIEWERS,
    PERM_ACCESS_AGENCY_PORTAL,
}

# ---------------------------------------------------------------------------
# Role → permissions matrix (Phase 0 specification)
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[UserRole, Set[str]] = {
    UserRole.ADMIN: ALL_PERMISSIONS,

    UserRole.BRAND_MANAGER: {
        PERM_MANAGE_CONSTITUTION,
        PERM_APPROVE_FINDINGS,
        PERM_APPROVE_DOCS,
        PERM_ASSIGN_REVIEWERS,
        PERM_VIEW_ANALYTICS,
        PERM_VIEW_AUDIT_LOGS,
        PERM_UPLOAD_DOCS,
        PERM_RUN_ANALYSIS,
    },

    UserRole.REVIEWER: {
        PERM_APPROVE_DOCS,
        PERM_ASSIGN_REVIEWERS,
        PERM_VIEW_ANALYTICS,
        PERM_UPLOAD_DOCS,
        PERM_RUN_ANALYSIS,
    },

    UserRole.LEGAL_REVIEWER: {
        PERM_APPROVE_LEGAL,
        PERM_VIEW_AUDIT_LOGS,
        PERM_VIEW_ANALYTICS,
        PERM_UPLOAD_DOCS,
        PERM_RUN_ANALYSIS,
    },

    UserRole.CONTENT_CREATOR: {
        PERM_UPLOAD_DOCS,
        PERM_RUN_ANALYSIS,
        PERM_READ_OWN_DOCS,
    },

    UserRole.EXTERNAL_AGENCY: {
        PERM_ACCESS_AGENCY_PORTAL,
        PERM_UPLOAD_DOCS,
        PERM_RUN_ANALYSIS,
    },

    UserRole.LEADERSHIP: {
        PERM_VIEW_ANALYTICS,
        PERM_VIEW_AUDIT_LOGS,
    },
}


def _get_user_permissions(role: UserRole) -> Set[str]:
    return ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------

def require_permission(permission: str):
    """
    Returns a FastAPI dependency that raises HTTP 403 if the current user's
    role does not have *permission*.

    Usage::

        @router.get("/...", dependencies=[Depends(require_permission("manage_users"))])
    """
    # Import here to avoid circular import at module load time.
    from app.auth.dependencies import get_current_active_user
    from app.models.user import User

    def _check(current_user: User = Depends(get_current_active_user)) -> User:
        if permission not in _get_user_permissions(current_user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required.",
            )
        return current_user

    return _check


def require_role(*roles: UserRole):
    """
    Returns a FastAPI dependency that raises HTTP 403 if the current user's
    role is not in *roles*.

    Usage::

        @router.delete("/...", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """
    from app.auth.dependencies import get_current_active_user
    from app.models.user import User

    def _check(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role.",
            )
        return current_user

    return _check


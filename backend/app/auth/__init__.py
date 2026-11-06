"""
app/auth/__init__.py
Exports the auth sub-package symbols for convenient importing.
"""
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token, decode_token
from app.auth.dependencies import get_current_user, get_current_active_user
from app.auth.rbac import ROLE_PERMISSIONS, require_permission, require_role

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "get_current_active_user",
    "ROLE_PERMISSIONS",
    "require_permission",
    "require_role",
]


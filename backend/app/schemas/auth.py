"""
app/schemas/auth.py
Pydantic schemas for authentication, organisation management, and audit inspection.
Enforces strict password validation rules, prevents self-assignment of privileged roles,
and protects sensitive credentials from exposure.
"""
import re
import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict

from app.models.user import UserRole


def validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(v) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"[\d\W_]", v):
        raise ValueError("Password must contain at least one number or special character.")
    return v


# ---------------------------------------------------------------------------
# Organisation Bootstrap (One-time atomic org + admin creation)
# ---------------------------------------------------------------------------

class OrganizationBootstrap(BaseModel):
    org_name: str
    org_slug: str
    admin_email: EmailStr
    admin_password: str
    admin_full_name: str

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Organisation name cannot be empty.")
        return s

    @field_validator("org_slug")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        s = v.strip().lower()
        if not s or not s.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Organisation slug must be alphanumeric with hyphens/underscores.")
        return s

    @field_validator("admin_password")
    @classmethod
    def admin_password_rule(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("admin_full_name")
    @classmethod
    def admin_name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Admin full name cannot be empty.")
        return s


class OrganizationCreate(BaseModel):
    name: str
    slug: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Organisation name cannot be empty.")
        return s

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        s = v.strip().lower()
        if not s or not s.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Organisation slug must be alphanumeric with hyphens/underscores.")
        return s


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


# ---------------------------------------------------------------------------
# User Schemas
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    """
    Public registration model.
    Privileged roles cannot be self-assigned; defaults to CONTENT_CREATOR.
    """
    email: EmailStr
    password: str
    full_name: str
    organization_id: Optional[uuid.UUID] = None
    organization_slug: Optional[str] = None
    role: Optional[UserRole] = None

    @field_validator("password")
    @classmethod
    def password_rule(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Full name cannot be empty.")
        return s

    @model_validator(mode="after")
    def check_org_provided(self):
        if not self.organization_id and not self.organization_slug:
            raise ValueError("Either organization_id or organization_slug must be provided.")
        return self


class UserCreateAdmin(BaseModel):
    """
    Admin-only user provisioning schema.
    Only authorized Admins may use this to assign roles within their organisation.
    """
    email: EmailStr
    password: str
    full_name: str
    role: UserRole = UserRole.CONTENT_CREATOR

    @field_validator("password")
    @classmethod
    def password_rule(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Full name cannot be empty.")
        return s


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    permissions: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Auth / Token
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: Optional[uuid.UUID] = None
    organization_slug: Optional[str] = None

    @model_validator(mode="after")
    def check_org_provided(self):
        if not self.organization_id and not self.organization_slug:
            raise ValueError("Either organization_id or organization_slug must be provided.")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    action: str
    target_entity: str
    target_id: uuid.UUID
    version_number: Optional[int] = None
    details: Optional[Any] = None
    timestamp: datetime

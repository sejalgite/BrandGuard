"""
app/schemas/constitution.py
Pydantic schemas for Brand Constitution, Rules, Facts, Terms, and Assets.
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.constitution import RuleCategory, EntityStatus


# ---------------------------------------------------------------------------
# Overview Schemas
# ---------------------------------------------------------------------------

class ConstitutionOverviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    constitution_id: uuid.UUID
    title: str
    version: str
    total_rules: int
    approved_rules: int
    pending_rules: int
    total_facts: int
    approved_facts: int
    expired_facts: int
    total_terms: int
    prohibited_terms: int
    total_assets: int
    pending_approvals: int


# ---------------------------------------------------------------------------
# Brand Rules Schemas
# ---------------------------------------------------------------------------

class BrandRuleCreate(BaseModel):
    rule_code: str
    category: RuleCategory
    title: str
    description: str
    examples_positive: Optional[List[str]] = []
    examples_negative: Optional[List[str]] = []
    status: Optional[EntityStatus] = EntityStatus.DRAFT

    @field_validator("rule_code")
    @classmethod
    def clean_rule_code(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Rule code cannot be empty.")
        return s

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Rule title cannot be empty.")
        return s


class BrandRuleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[RuleCategory] = None
    examples_positive: Optional[List[str]] = None
    examples_negative: Optional[List[str]] = None


class BrandRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    constitution_id: uuid.UUID
    rule_code: str
    category: RuleCategory
    title: str
    description: str
    examples_positive: Optional[List[str]] = None
    examples_negative: Optional[List[str]] = None
    status: EntityStatus
    approved_by: Optional[uuid.UUID] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Fact Registry Schemas
# ---------------------------------------------------------------------------

class FactRegistryCreate(BaseModel):
    fact_code: str
    claim_type: str
    statement: str
    numerical_value: Optional[Decimal] = None
    unit: Optional[str] = None
    source_reference: str
    fact_owner: str
    expiry_date: date
    status: Optional[EntityStatus] = EntityStatus.DRAFT

    @field_validator("fact_code")
    @classmethod
    def clean_fact_code(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Fact code cannot be empty.")
        return s


class FactRegistryUpdate(BaseModel):
    claim_type: Optional[str] = None
    statement: Optional[str] = None
    numerical_value: Optional[Decimal] = None
    unit: Optional[str] = None
    source_reference: Optional[str] = None
    fact_owner: Optional[str] = None
    expiry_date: Optional[date] = None


class FactRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    constitution_id: uuid.UUID
    fact_code: str
    claim_type: str
    statement: str
    numerical_value: Optional[Decimal] = None
    unit: Optional[str] = None
    source_reference: str
    fact_owner: str
    expiry_date: date
    is_expired: bool = False
    status: EntityStatus
    approved_by: Optional[uuid.UUID] = None
    created_at: datetime


class FactConflictOut(BaseModel):
    claim_type: str
    conflicting_facts: List[FactRegistryOut]
    conflict_reason: str


# ---------------------------------------------------------------------------
# Term Bank Schemas
# ---------------------------------------------------------------------------

class TermBankCreate(BaseModel):
    term_code: str
    prohibited_term: str
    preferred_term: str
    usage_context: Optional[str] = None
    is_case_sensitive: bool = False
    status: Optional[EntityStatus] = EntityStatus.ACTIVE

    @field_validator("term_code")
    @classmethod
    def clean_term_code(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Term code cannot be empty.")
        return s


class TermBankUpdate(BaseModel):
    prohibited_term: Optional[str] = None
    preferred_term: Optional[str] = None
    usage_context: Optional[str] = None
    is_case_sensitive: Optional[bool] = None


class TermBankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    constitution_id: uuid.UUID
    term_code: str
    prohibited_term: str
    preferred_term: str
    usage_context: Optional[str] = None
    is_case_sensitive: bool
    status: EntityStatus
    created_at: datetime


# ---------------------------------------------------------------------------
# Brand Asset Schemas
# ---------------------------------------------------------------------------

class BrandAssetCreate(BaseModel):
    asset_code: str
    asset_type: str  # COLOR, LOGO, TYPOGRAPHY, ICON, BANNER
    name: str
    specifications: Dict[str, Any]
    status: Optional[EntityStatus] = EntityStatus.ACTIVE


class BrandAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    constitution_id: uuid.UUID
    asset_code: str
    asset_type: str
    name: str
    specifications: Dict[str, Any]
    file_path: Optional[str] = None
    status: EntityStatus
    created_at: datetime


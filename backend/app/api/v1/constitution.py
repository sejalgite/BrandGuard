"""
app/api/v1/constitution.py
Brand Constitution Builder and Fact Registry API Endpoints.
Covers:
- Constitution overview and governance metrics.
- Brand Rules management, submission, approval, and rejection.
- Fact Registry with dynamic expiration detection and conflict surfacing.
- Term Bank with preferred and prohibited vocabulary.
- Brand Asset Library with safe file upload and brand color management.
- Multi-tenant scoping and audit logging for all mutations.
"""
import os
import re
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, UploadFile, File, Form,
    status
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, BrandAsset,
    RuleCategory, EntityStatus
)
from app.models.user import User
from app.auth.dependencies import get_current_active_user
from app.auth.rbac import (
    require_permission,
    PERM_MANAGE_CONSTITUTION,
    PERM_UPLOAD_DOCS,
    PERM_VIEW_ANALYTICS,
)
from app.audit.audit_logger import log_action
from app.schemas.constitution import (
    ConstitutionOverviewOut,
    BrandRuleCreate,
    BrandRuleUpdate,
    BrandRuleOut,
    FactRegistryCreate,
    FactRegistryUpdate,
    FactRegistryOut,
    FactConflictOut,
    TermBankCreate,
    TermBankUpdate,
    TermBankOut,
    BrandAssetCreate,
    BrandAssetOut,
)

router = APIRouter()

STORAGE_BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "assets")
)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_or_create_constitution(org_id: uuid.UUID, db: Session) -> BrandConstitution:
    """Ensure an active constitution exists for the organisation."""
    constitution = (
        db.query(BrandConstitution)
        .filter(
            BrandConstitution.organization_id == org_id,
            BrandConstitution.is_active == True,
        )
        .first()
    )
    if not constitution:
        constitution = BrandConstitution(
            id=uuid.uuid4(),
            organization_id=org_id,
            title="ApexCloud Core Governance Constitution",
            version="1.0",
            is_active=True,
        )
        db.add(constitution)
        db.commit()
        db.refresh(constitution)
    return constitution


def _fact_to_out(fact: FactRegistry) -> FactRegistryOut:
    is_exp = fact.expiry_date < date.today()
    status_val = EntityStatus.EXPIRED if is_exp else fact.status
    out = FactRegistryOut.model_validate(fact)
    out.is_expired = is_exp
    out.status = status_val
    return out


# ---------------------------------------------------------------------------
# 1. Constitution Overview
# ---------------------------------------------------------------------------

@router.get(
    "/overview",
    response_model=ConstitutionOverviewOut,
    summary="Retrieve governance metrics and Constitution summary",
)
def get_constitution_overview(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    cid = constitution.id
    oid = current_user.organization_id

    # Rules metrics
    rules = db.query(BrandRule).filter(BrandRule.organization_id == oid, BrandRule.constitution_id == cid).all()
    total_rules = len(rules)
    approved_rules = sum(1 for r in rules if r.status == EntityStatus.ACTIVE)
    pending_rules = sum(1 for r in rules if r.status == EntityStatus.PENDING_APPROVAL)

    # Facts metrics
    facts = db.query(FactRegistry).filter(FactRegistry.organization_id == oid, FactRegistry.constitution_id == cid).all()
    today = date.today()
    total_facts = len(facts)
    approved_facts = sum(1 for f in facts if f.status == EntityStatus.ACTIVE and f.expiry_date >= today)
    expired_facts = sum(1 for f in facts if f.expiry_date < today)

    # Terms metrics
    terms = db.query(TermBank).filter(TermBank.organization_id == oid, TermBank.constitution_id == cid).all()
    total_terms = len(terms)
    prohibited_terms = sum(1 for t in terms if t.status == EntityStatus.ACTIVE and t.prohibited_term)

    # Assets metrics
    assets = db.query(BrandAsset).filter(BrandAsset.organization_id == oid, BrandAsset.constitution_id == cid).all()
    total_assets = len(assets)

    pending_approvals = pending_rules + sum(1 for f in facts if f.status == EntityStatus.PENDING_APPROVAL)

    return ConstitutionOverviewOut(
        constitution_id=cid,
        title=constitution.title,
        version=constitution.version,
        total_rules=total_rules,
        approved_rules=approved_rules,
        pending_rules=pending_rules,
        total_facts=total_facts,
        approved_facts=approved_facts,
        expired_facts=expired_facts,
        total_terms=total_terms,
        prohibited_terms=prohibited_terms,
        total_assets=total_assets,
        pending_approvals=pending_approvals,
    )


# ---------------------------------------------------------------------------
# 2. Brand Rules
# ---------------------------------------------------------------------------

@router.get(
    "/rules",
    response_model=List[BrandRuleOut],
    summary="List Brand Rules with category and status filters",
)
def list_brand_rules(
    category: Optional[RuleCategory] = None,
    status_filter: Optional[EntityStatus] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    query = db.query(BrandRule).filter(
        BrandRule.organization_id == current_user.organization_id,
        BrandRule.constitution_id == constitution.id,
    )

    if category:
        query = query.filter(BrandRule.category == category)
    if status_filter:
        query = query.filter(BrandRule.status == status_filter)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((BrandRule.title.ilike(s)) | (BrandRule.description.ilike(s)) | (BrandRule.rule_code.ilike(s)))

    return query.order_by(BrandRule.rule_code.asc()).all()


@router.post(
    "/rules",
    response_model=BrandRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft Brand Rule",
)
def create_brand_rule(
    payload: BrandRuleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)

    # Check rule_code uniqueness within constitution
    existing = db.query(BrandRule).filter(
        BrandRule.constitution_id == constitution.id,
        BrandRule.rule_code == payload.rule_code,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule code '{payload.rule_code}' already exists in this Constitution.",
        )

    rule = BrandRule(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        constitution_id=constitution.id,
        rule_code=payload.rule_code,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        examples_positive=payload.examples_positive or [],
        examples_negative=payload.examples_negative or [],
        status=payload.status or EntityStatus.DRAFT,
        approved_by=None,
    )
    db.add(rule)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="RULE_CREATED",
        target_entity="BRAND_RULE",
        target_id=rule.id,
        details={"rule_code": rule.rule_code, "category": rule.category.value, "status": rule.status.value},
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.get(
    "/rules/{rule_id}",
    response_model=BrandRuleOut,
    summary="Get single Brand Rule by ID",
)
def get_brand_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BrandRule).filter(
        BrandRule.id == rule_id,
        BrandRule.organization_id == current_user.organization_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Brand Rule not found in your organisation.")
    return rule


@router.put(
    "/rules/{rule_id}",
    response_model=BrandRuleOut,
    summary="Update Brand Rule content",
)
def update_brand_rule(
    rule_id: uuid.UUID,
    payload: BrandRuleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BrandRule).filter(
        BrandRule.id == rule_id,
        BrandRule.organization_id == current_user.organization_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Brand Rule not found in your organisation.")

    if payload.title is not None:
        rule.title = payload.title
    if payload.description is not None:
        rule.description = payload.description
    if payload.category is not None:
        rule.category = payload.category
    if payload.examples_positive is not None:
        rule.examples_positive = payload.examples_positive
    if payload.examples_negative is not None:
        rule.examples_negative = payload.examples_negative

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="RULE_UPDATED",
        target_entity="BRAND_RULE",
        target_id=rule.id,
        details={"rule_code": rule.rule_code},
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/rules/{rule_id}/submit",
    response_model=BrandRuleOut,
    summary="Submit a draft Brand Rule for approval",
)
def submit_brand_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BrandRule).filter(
        BrandRule.id == rule_id,
        BrandRule.organization_id == current_user.organization_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Brand Rule not found.")

    rule.status = EntityStatus.PENDING_APPROVAL
    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="RULE_SUBMITTED_FOR_APPROVAL",
        target_entity="BRAND_RULE",
        target_id=rule.id,
        details={"rule_code": rule.rule_code},
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/rules/{rule_id}/approve",
    response_model=BrandRuleOut,
    summary="Approve a Brand Rule (Authorized roles only)",
    dependencies=[Depends(require_permission(PERM_MANAGE_CONSTITUTION))],
)
def approve_brand_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BrandRule).filter(
        BrandRule.id == rule_id,
        BrandRule.organization_id == current_user.organization_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Brand Rule not found.")

    rule.status = EntityStatus.ACTIVE
    rule.approved_by = current_user.id

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="RULE_APPROVED",
        target_entity="BRAND_RULE",
        target_id=rule.id,
        details={"rule_code": rule.rule_code, "approved_by": str(current_user.id)},
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/rules/{rule_id}/reject",
    response_model=BrandRuleOut,
    summary="Reject a Brand Rule (Authorized roles only)",
    dependencies=[Depends(require_permission(PERM_MANAGE_CONSTITUTION))],
)
def reject_brand_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BrandRule).filter(
        BrandRule.id == rule_id,
        BrandRule.organization_id == current_user.organization_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Brand Rule not found.")

    rule.status = EntityStatus.REJECTED
    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="RULE_REJECTED",
        target_entity="BRAND_RULE",
        target_id=rule.id,
        details={"rule_code": rule.rule_code},
    )
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# 3. Fact Registry
# ---------------------------------------------------------------------------

@router.get(
    "/facts",
    response_model=List[FactRegistryOut],
    summary="List registered brand facts with live expiration checks",
)
def list_facts(
    status_filter: Optional[EntityStatus] = None,
    claim_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    query = db.query(FactRegistry).filter(
        FactRegistry.organization_id == current_user.organization_id,
        FactRegistry.constitution_id == constitution.id,
    )

    if claim_type:
        query = query.filter(FactRegistry.claim_type.ilike(f"%{claim_type.strip()}%"))
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((FactRegistry.statement.ilike(s)) | (FactRegistry.fact_code.ilike(s)) | (FactRegistry.fact_owner.ilike(s)))

    facts = query.order_by(FactRegistry.fact_code.asc()).all()
    results = [_fact_to_out(f) for f in facts]

    if status_filter:
        results = [r for r in results if r.status == status_filter]

    return results


@router.post(
    "/facts",
    response_model=FactRegistryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Brand Fact",
)
def create_fact(
    payload: FactRegistryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)

    existing = db.query(FactRegistry).filter(
        FactRegistry.constitution_id == constitution.id,
        FactRegistry.fact_code == payload.fact_code,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Fact code '{payload.fact_code}' already exists in this Constitution.",
        )

    fact = FactRegistry(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        constitution_id=constitution.id,
        fact_code=payload.fact_code,
        claim_type=payload.claim_type,
        statement=payload.statement,
        numerical_value=payload.numerical_value,
        unit=payload.unit,
        source_reference=payload.source_reference,
        fact_owner=payload.fact_owner,
        expiry_date=payload.expiry_date,
        status=payload.status or EntityStatus.DRAFT,
        approved_by=None,
    )
    db.add(fact)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="FACT_CREATED",
        target_entity="FACT_REGISTRY",
        target_id=fact.id,
        details={"fact_code": fact.fact_code, "claim_type": fact.claim_type},
    )
    db.commit()
    db.refresh(fact)
    return _fact_to_out(fact)


@router.get(
    "/facts/conflicts/detect",
    response_model=List[FactConflictOut],
    summary="Surface conflicting or contradictory brand facts",
)
def detect_fact_conflicts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Identifies facts claiming the same claim_type with disparate numerical values or contradictory statements.
    Ensures conflicts are surfaced visibly rather than silently overwritten.
    """
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    facts = (
        db.query(FactRegistry)
        .filter(
            FactRegistry.organization_id == current_user.organization_id,
            FactRegistry.constitution_id == constitution.id,
            FactRegistry.status.in_([EntityStatus.ACTIVE, EntityStatus.PENDING_APPROVAL]),
        )
        .all()
    )

    by_claim: dict[str, list[FactRegistry]] = {}
    for f in facts:
        by_claim.setdefault(f.claim_type.strip().lower(), []).append(f)

    conflicts: List[FactConflictOut] = []
    for claim, flist in by_claim.items():
        if len(flist) > 1:
            # Check for disparate values
            values = {f.numerical_value for f in flist if f.numerical_value is not None}
            if len(values) > 1:
                conflicts.append(FactConflictOut(
                    claim_type=claim,
                    conflicting_facts=[_fact_to_out(f) for f in flist],
                    conflict_reason=f"Multiple active facts define conflicting numerical values: {sorted(list(values))}",
                ))

    return conflicts


@router.post(
    "/facts/{fact_id}/approve",
    response_model=FactRegistryOut,
    summary="Approve a brand fact (Authorized roles only)",
    dependencies=[Depends(require_permission(PERM_MANAGE_CONSTITUTION))],
)
def approve_fact(
    fact_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    fact = db.query(FactRegistry).filter(
        FactRegistry.id == fact_id,
        FactRegistry.organization_id == current_user.organization_id,
    ).first()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found.")

    fact.status = EntityStatus.ACTIVE
    fact.approved_by = current_user.id

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="FACT_APPROVED",
        target_entity="FACT_REGISTRY",
        target_id=fact.id,
        details={"fact_code": fact.fact_code, "approved_by": str(current_user.id)},
    )
    db.commit()
    db.refresh(fact)
    return _fact_to_out(fact)


# ---------------------------------------------------------------------------
# 4. Term Bank
# ---------------------------------------------------------------------------

@router.get(
    "/terms",
    response_model=List[TermBankOut],
    summary="List preferred and prohibited terminology",
)
def list_terms(
    search: Optional[str] = None,
    status_filter: Optional[EntityStatus] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    query = db.query(TermBank).filter(
        TermBank.organization_id == current_user.organization_id,
        TermBank.constitution_id == constitution.id,
    )

    if status_filter:
        query = query.filter(TermBank.status == status_filter)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (TermBank.prohibited_term.ilike(s)) |
            (TermBank.preferred_term.ilike(s)) |
            (TermBank.term_code.ilike(s))
        )

    return query.order_by(TermBank.term_code.asc()).all()


@router.post(
    "/terms",
    response_model=TermBankOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create preferred and prohibited vocabulary entry",
)
def create_term(
    payload: TermBankCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)

    existing = db.query(TermBank).filter(
        TermBank.constitution_id == constitution.id,
        TermBank.term_code == payload.term_code,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Term code '{payload.term_code}' already exists in this Constitution.",
        )

    term = TermBank(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        constitution_id=constitution.id,
        term_code=payload.term_code,
        prohibited_term=payload.prohibited_term,
        preferred_term=payload.preferred_term,
        usage_context=payload.usage_context,
        is_case_sensitive=payload.is_case_sensitive,
        status=payload.status or EntityStatus.ACTIVE,
    )
    db.add(term)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="TERM_CREATED",
        target_entity="TERM_BANK",
        target_id=term.id,
        details={"term_code": term.term_code, "prohibited": term.prohibited_term, "preferred": term.preferred_term},
    )
    db.commit()
    db.refresh(term)
    return term


# ---------------------------------------------------------------------------
# 5. Brand Assets (Colors, Logos, Files)
# ---------------------------------------------------------------------------

@router.get(
    "/assets",
    response_model=List[BrandAssetOut],
    summary="List approved brand assets and visual identity tokens",
)
def list_assets(
    asset_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    query = db.query(BrandAsset).filter(
        BrandAsset.organization_id == current_user.organization_id,
        BrandAsset.constitution_id == constitution.id,
    )
    if asset_type:
        query = query.filter(BrandAsset.asset_type.ilike(asset_type.strip()))

    return query.order_by(BrandAsset.asset_code.asc()).all()


@router.post(
    "/assets",
    response_model=BrandAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register brand asset specification (e.g. brand color hex, typography)",
)
def create_asset_specification(
    payload: BrandAssetCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)

    existing = db.query(BrandAsset).filter(
        BrandAsset.constitution_id == constitution.id,
        BrandAsset.asset_code == payload.asset_code,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset code '{payload.asset_code}' already exists.",
        )

    asset = BrandAsset(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        constitution_id=constitution.id,
        asset_code=payload.asset_code,
        asset_type=payload.asset_type.upper(),
        name=payload.name,
        specifications=payload.specifications,
        file_path=None,
        status=payload.status or EntityStatus.ACTIVE,
    )
    db.add(asset)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="ASSET_CREATED",
        target_entity="BRAND_ASSET",
        target_id=asset.id,
        details={"asset_code": asset.asset_code, "type": asset.asset_type},
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.post(
    "/assets/upload",
    response_model=BrandAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Safely upload visual brand asset (PNG, JPG, SVG)",
)
async def upload_brand_asset(
    asset_code: str = Form(...),
    asset_type: str = Form("LOGO"),
    name: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Safe file upload handler:
    1. Validates extension against ALLOWED_EXTENSIONS.
    2. Validates file size (< 10MB).
    3. Prevents path traversal via sanitized filenames.
    4. Stores locally within tenant-isolated folder.
    """
    constitution = _get_or_create_constitution(current_user.organization_id, db)

    # Sanitize and validate extension
    filename = file.filename or "asset"
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' not permitted. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds maximum permitted limit (10 MB).",
        )

    # Safe destination directory
    org_folder = os.path.join(STORAGE_BASE_DIR, str(current_user.organization_id))
    os.makedirs(org_folder, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex[:12]}_{re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)}"
    dest_path = os.path.join(org_folder, safe_name)

    with open(dest_path, "wb") as f:
        f.write(content)

    asset = BrandAsset(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        constitution_id=constitution.id,
        asset_code=asset_code.strip().upper(),
        asset_type=asset_type.strip().upper(),
        name=name.strip(),
        specifications={"filename": filename, "size_bytes": len(content), "extension": ext},
        file_path=dest_path,
        status=EntityStatus.ACTIVE,
    )
    db.add(asset)
    db.flush()

    log_action(
        db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="ASSET_UPLOADED",
        target_entity="BRAND_ASSET",
        target_id=asset.id,
        details={"asset_code": asset.asset_code, "filename": safe_name},
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.get(
    "/assets/{asset_id}/file",
    summary="Safely stream uploaded brand asset",
)
def get_asset_file(
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    asset = db.query(BrandAsset).filter(
        BrandAsset.id == asset_id,
        BrandAsset.organization_id == current_user.organization_id,
    ).first()
    if not asset or not asset.file_path or not os.path.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="Asset file not found.")

    return FileResponse(asset.file_path)


# ---------------------------------------------------------------------------
# 6. Seed ApexCloud Technologies Demo Constitution
# ---------------------------------------------------------------------------

@router.post(
    "/seed-demo",
    summary="Seed comprehensive ApexCloud Technologies demo constitution data",
)
def seed_demo_constitution(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    constitution = _get_or_create_constitution(current_user.organization_id, db)
    cid = constitution.id
    oid = current_user.organization_id

    # Check if already seeded
    existing_rule = db.query(BrandRule).filter(BrandRule.constitution_id == cid).first()
    if existing_rule:
        return {"message": "Constitution already populated with brand rules."}

    # 1. ApexCloud Demo Rules
    demo_rules = [
        BrandRule(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            rule_code="TONE-001",
            category=RuleCategory.TONE_VOICE,
            title="Authoritative Yet Accessible Tone",
            description="Communications should convey enterprise reliability without bureaucratic jargon. Speak directly, confidently, and concisely.",
            examples_positive=["ApexCloud accelerates enterprise deployment by 40% with zero downtime.", "Scale seamlessly with our automated Kubernetes governance."],
            examples_negative=["We are literally the most magical cloud ever created in the universe.", "Our super-cool platform is cheap and foolproof."],
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        BrandRule(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            rule_code="STYLE-002",
            category=RuleCategory.WRITING_STYLE,
            title="Active Voice and Concrete Metrics",
            description="Use active voice in product feature descriptions. Avoid vague superlatives like 'world-leading' without citable evidence.",
            examples_positive=["ApexCloud protects over 10 million transactions daily.", "Our platform reduces cloud egress costs by 28%."],
            examples_negative=["Industry-leading outcomes are delivered by our best-in-class synergy.", "It has been said that we are the best."],
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        BrandRule(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            rule_code="VIS-003",
            category=RuleCategory.VISUAL,
            title="Primary Color Dominance",
            description="Marketing collateral must maintain Apex Blue (#1E40AF) or Dark Slate (#0F172A) as dominant backgrounds. Neon accents are prohibited.",
            examples_positive=["Hero headers must use Apex Blue gradient with minimum 60% coverage."],
            examples_negative=["Using neon lime green background for enterprise reports."],
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        BrandRule(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            rule_code="ACC-004",
            category=RuleCategory.ACCESSIBILITY,
            title="WCAG 2.1 AA Contrast Compliance",
            description="All text overlays on banners and imagery must maintain a contrast ratio of at least 4.5:1 for normal text and 3:1 for large headlines.",
            examples_positive=["White text (#FFFFFF) on Apex Blue (#1E40AF) achieves 8.6:1 contrast."],
            examples_negative=["Light grey text (#CBD5E1) placed over white backgrounds."],
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
    ]
    db.add_all(demo_rules)

    # 2. ApexCloud Demo Facts
    demo_facts = [
        FactRegistry(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            fact_code="FACT-PRICING-01",
            claim_type="Pricing",
            statement="ApexCloud Enterprise tier starts at $2,499 per month billed annually.",
            numerical_value=2499,
            unit="USD/month",
            source_reference="Q4 2025 Approved Enterprise Price Sheet v3.2",
            fact_owner="Finance & Product Marketing",
            expiry_date=date(2027, 12, 31),
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        FactRegistry(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            fact_code="FACT-SLA-02",
            claim_type="Availability SLA",
            statement="ApexCloud provides a guaranteed 99.99% multi-region uptime service level agreement.",
            numerical_value=99.99,
            unit="percent",
            source_reference="ApexCloud Master Services Agreement (MSA) Schedule B",
            fact_owner="Infrastructure Operations",
            expiry_date=date(2028, 1, 1),
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        FactRegistry(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            fact_code="FACT-COMPLIANCE-03",
            claim_type="Security Compliance",
            statement="ApexCloud holds SOC 2 Type II, ISO 27001, and HIPAA compliance certifications.",
            source_reference="Annual Security Audit Report 2025 by Ernst & Young",
            fact_owner="Chief Information Security Officer (CISO)",
            expiry_date=date(2027, 6, 30),
            status=EntityStatus.ACTIVE,
            approved_by=current_user.id,
        ),
        FactRegistry(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            fact_code="FACT-EXPIRED-LEGACY",
            claim_type="Legacy Promotion",
            statement="ApexCloud Starter tier was $49/month with free migration support.",
            numerical_value=49,
            unit="USD/month",
            source_reference="2022 Discontinued Promotional Tariff",
            fact_owner="Product Marketing",
            expiry_date=date(2023, 1, 1),  # Intentionally expired for acceptance tests
            status=EntityStatus.EXPIRED,
            approved_by=current_user.id,
        ),
    ]
    db.add_all(demo_facts)

    # 3. ApexCloud Demo Term Bank
    demo_terms = [
        TermBank(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            term_code="TERM-01",
            prohibited_term="unbreakable",
            preferred_term="enterprise-grade resilience",
            usage_context="Never claim technology is unbreakable; use enterprise resilience instead.",
            is_case_sensitive=False,
            status=EntityStatus.ACTIVE,
        ),
        TermBank(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            term_code="TERM-02",
            prohibited_term="cheap cloud",
            preferred_term="cost-efficient cloud infrastructure",
            usage_context="Preserve premium enterprise brand posture. Avoid 'cheap'.",
            is_case_sensitive=False,
            status=EntityStatus.ACTIVE,
        ),
        TermBank(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            term_code="TERM-03",
            prohibited_term="foolproof setup",
            preferred_term="streamlined zero-touch onboarding",
            usage_context="Avoid disparaging users; highlight intuitive automation.",
            is_case_sensitive=False,
            status=EntityStatus.ACTIVE,
        ),
    ]
    db.add_all(demo_terms)

    # 4. ApexCloud Demo Assets (Brand Colors)
    demo_assets = [
        BrandAsset(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            asset_code="COLOR-PRIMARY",
            asset_type="COLOR",
            name="Apex Blue",
            specifications={"hex": "#1E40AF", "rgb": "30, 64, 175", "usage": "Primary brand color for logos, buttons, and hero elements"},
            status=EntityStatus.ACTIVE,
        ),
        BrandAsset(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            asset_code="COLOR-CYBER",
            asset_type="COLOR",
            name="Cyber Indigo",
            specifications={"hex": "#4F46E5", "rgb": "79, 70, 229", "usage": "Secondary gradient and accent highlight"},
            status=EntityStatus.ACTIVE,
        ),
        BrandAsset(
            id=uuid.uuid4(),
            organization_id=oid,
            constitution_id=cid,
            asset_code="COLOR-SLATE",
            asset_type="COLOR",
            name="Dark Slate",
            specifications={"hex": "#0F172A", "rgb": "15, 23, 42", "usage": "Dark mode background and executive typography"},
            status=EntityStatus.ACTIVE,
        ),
    ]
    db.add_all(demo_assets)

    db.commit()
    return {"message": "ApexCloud demo constitution populated successfully."}


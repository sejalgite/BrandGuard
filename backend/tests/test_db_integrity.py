import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError


def test_database_integrity_suite(db_session):
    """
    Genuine PostgreSQL 18 integrity test suite executing against live PostgreSQL with pgvector.
    Tests do NOT catch their own exceptions internally in SQL; SQLAlchemy directly verifies
    that PostgreSQL rejects illegal operations with IntegrityError or InternalError (triggers).
    """

    # 1. Setup Tenant Fixtures with unique slugs
    unique_suffix = uuid.uuid4().hex[:8]
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    const_a_id = str(uuid.uuid4())
    rule_a_id = str(uuid.uuid4())
    doc_a1_id = str(uuid.uuid4())
    doc_a2_id = str(uuid.uuid4())
    ver_a1_id = str(uuid.uuid4())
    ver_a2_id = str(uuid.uuid4())
    job_a1_id = str(uuid.uuid4())
    finding_a1_id = str(uuid.uuid4())
    comment_a1_id = str(uuid.uuid4())

    db_session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Tenant A', :slug)"),
        {"id": org_a_id, "slug": f"tenant-a-{unique_suffix}"}
    )
    db_session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Tenant B', :slug)"),
        {"id": org_b_id, "slug": f"tenant-b-{unique_suffix}"}
    )

    db_session.execute(text("""
        INSERT INTO users (id, organization_id, email, hashed_password, full_name, role)
        VALUES (:id, :org_id, :email, 'pwd_hash', 'Alice A', 'ADMIN')
    """), {"id": user_a_id, "org_id": org_a_id, "email": f"alice_{unique_suffix}@a.com"})

    db_session.execute(text("""
        INSERT INTO users (id, organization_id, email, hashed_password, full_name, role)
        VALUES (:id, :org_id, :email, 'pwd_hash', 'Bob B', 'ADMIN')
    """), {"id": user_b_id, "org_id": org_b_id, "email": f"bob_{unique_suffix}@b.com"})

    db_session.execute(text("""
        INSERT INTO brand_constitutions (id, organization_id, title)
        VALUES (:id, :org_id, 'Constitution A')
    """), {"id": const_a_id, "org_id": org_a_id})

    db_session.execute(text("""
        INSERT INTO brand_rules (id, organization_id, constitution_id, rule_code, category, title, description)
        VALUES (:id, :org_id, :const_id, 'TONE-01', 'TONE_VOICE', 'Authoritative Voice', 'Speak with authority')
    """), {"id": rule_a_id, "org_id": org_a_id, "const_id": const_a_id})

    db_session.execute(text("""
        INSERT INTO documents (id, organization_id, creator_id, title, content_type)
        VALUES (:id, :org_id, :creator_id, 'Document A1', 'TEXT')
    """), {"id": doc_a1_id, "org_id": org_a_id, "creator_id": user_a_id})

    db_session.execute(text("""
        INSERT INTO documents (id, organization_id, creator_id, title, content_type)
        VALUES (:id, :org_id, :creator_id, 'Document A2', 'TEXT')
    """), {"id": doc_a2_id, "org_id": org_a_id, "creator_id": user_a_id})

    db_session.execute(text("""
        INSERT INTO document_versions (id, organization_id, document_id, version_number, raw_content, is_locked)
        VALUES (:id, :org_id, :doc_id, 1, 'Draft content V1', FALSE)
    """), {"id": ver_a1_id, "org_id": org_a_id, "doc_id": doc_a1_id})

    db_session.execute(text("""
        INSERT INTO document_versions (id, organization_id, document_id, version_number, raw_content, is_locked)
        VALUES (:id, :org_id, :doc_id, 1, 'Draft content V2', FALSE)
    """), {"id": ver_a2_id, "org_id": org_a_id, "doc_id": doc_a2_id})

    db_session.execute(text("""
        INSERT INTO review_jobs (id, organization_id, document_id, version_id, status)
        VALUES (:id, :org_id, :doc_id, :ver_id, 'COMPLETED')
    """), {"id": job_a1_id, "org_id": org_a_id, "doc_id": doc_a1_id, "ver_id": ver_a1_id})

    db_session.execute(text("""
        INSERT INTO findings (
            id, organization_id, constitution_id, document_id, version_id, job_id,
            category, severity, confidence, flagged_snippet, explanation,
            evidence_type, rule_id, cited_code, source, verified_by_gate
        ) VALUES (
            :id, :org_id, :const_id, :doc_id, :ver_id, :job_id,
            'TONE', 'HIGH', 0.900, 'flimsy snippet', 'Tone clash',
            'RULE', :rule_id, 'TONE-01', 'LIVE_LLM', TRUE
        )
    """), {
        "id": finding_a1_id, "org_id": org_a_id, "const_id": const_a_id,
        "doc_id": doc_a1_id, "ver_id": ver_a1_id, "job_id": job_a1_id,
        "rule_id": rule_a_id
    })

    db_session.execute(text("""
        INSERT INTO comments (id, organization_id, document_id, version_id, finding_id, user_id, content)
        VALUES (:id, :org_id, :doc_id, :ver_id, :finding_id, :user_id, 'Please review this')
    """), {
        "id": comment_a1_id, "org_id": org_a_id, "doc_id": doc_a1_id,
        "ver_id": ver_a1_id, "finding_id": finding_a1_id, "user_id": user_a_id
    })
    db_session.commit()

    # -------------------------------------------------------------------------
    # Test (a): Cross-organization references are rejected by Foreign Key
    # -------------------------------------------------------------------------
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO documents (id, organization_id, creator_id, title, content_type)
            VALUES (:id, :org_b, :creator_a, 'Illegal Cross-Tenant Doc', 'TEXT')
        """), {"id": str(uuid.uuid4()), "org_b": org_b_id, "creator_a": user_a_id})
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (b): A version cannot be paired with another document in same org
    # -------------------------------------------------------------------------
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO review_jobs (id, organization_id, document_id, version_id, status)
            VALUES (:id, :org_a, :doc_a1, :ver_a2, 'RUNNING')
        """), {"id": str(uuid.uuid4()), "org_a": org_a_id, "doc_a1": doc_a1_id, "ver_a2": ver_a2_id})
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (c): A comment cannot reply to a comment from another tenant
    # -------------------------------------------------------------------------
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO comments (id, organization_id, document_id, version_id, user_id, parent_comment_id, content)
            VALUES (:id, :org_b, :doc_a1, :ver_a1, :user_b, :parent_comment, 'Illegal cross-tenant reply')
        """), {
            "id": str(uuid.uuid4()), "org_b": org_b_id, "doc_a1": doc_a1_id,
            "ver_a1": ver_a1_id, "user_b": user_b_id, "parent_comment": comment_a1_id
        })
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (d): A finding cannot be referenced by a dispute from another tenant
    # -------------------------------------------------------------------------
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO disputes (id, organization_id, finding_id, user_id, justification)
            VALUES (:id, :org_b, :finding_a, :user_b, 'Cross-tenant dispute attempt')
        """), {
            "id": str(uuid.uuid4()), "org_b": org_b_id, "finding_a": finding_a1_id, "user_b": user_b_id
        })
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (e): Deleting a referenced user is prevented by ON DELETE RESTRICT
    # -------------------------------------------------------------------------
    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_a_id})
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (f): An unlocked draft can be deleted if defined policy permits
    # -------------------------------------------------------------------------
    draft_id = str(uuid.uuid4())
    db_session.execute(text("""
        INSERT INTO document_versions (id, organization_id, document_id, version_number, raw_content, is_locked)
        VALUES (:id, :org_a, :doc_a2, 99, 'Draft to delete', FALSE)
    """), {"id": draft_id, "org_a": org_a_id, "doc_a2": doc_a2_id})
    db_session.commit()

    del_res = db_session.execute(text("DELETE FROM document_versions WHERE id = :id"), {"id": draft_id})
    db_session.commit()
    assert del_res.rowcount == 1

    # -------------------------------------------------------------------------
    # Test (g): An approved locked version cannot be updated or deleted
    # -------------------------------------------------------------------------
    db_session.execute(text("""
        UPDATE document_versions SET is_locked = TRUE, version_status = 'APPROVED' WHERE id = :id
    """), {"id": ver_a1_id})
    db_session.commit()

    # Update attempt on locked version fails
    with pytest.raises(InternalError) as exc_update:
        db_session.execute(text("UPDATE document_versions SET raw_content = 'Hacked' WHERE id = :id"), {"id": ver_a1_id})
    assert "Database Guard: Document Version" in str(exc_update.value)
    db_session.rollback()

    # Delete attempt on locked version fails
    with pytest.raises(InternalError) as exc_delete:
        db_session.execute(text("DELETE FROM document_versions WHERE id = :id"), {"id": ver_a1_id})
    assert "Database Guard: Document Version" in str(exc_delete.value)
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (h): Audit and AI disclosure logs remain append-only
    # -------------------------------------------------------------------------
    audit_id = str(uuid.uuid4())
    db_session.execute(text("""
        INSERT INTO audit_logs (id, organization_id, actor_id, action, target_entity, target_id)
        VALUES (:id, :org_a, :actor, 'TEST_ACTION', 'DOC', :target_id)
    """), {"id": audit_id, "org_a": org_a_id, "actor": user_a_id, "target_id": doc_a1_id})
    db_session.commit()

    with pytest.raises(InternalError) as exc_audit_update:
        db_session.execute(text("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = :id"), {"id": audit_id})
    assert "strictly append-only" in str(exc_audit_update.value)
    db_session.rollback()

    with pytest.raises(InternalError) as exc_audit_delete:
        db_session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": audit_id})
    assert "strictly append-only" in str(exc_audit_delete.value)
    db_session.rollback()

    # -------------------------------------------------------------------------
    # Test (i): Additional Safeguards (APPROVED requires is_locked, bounds checks)
    # -------------------------------------------------------------------------
    # 1. APPROVED requires is_locked = TRUE
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO document_versions (id, organization_id, document_id, version_number, version_status, is_locked)
            VALUES (:id, :org_a, :doc_a1, 5, 'APPROVED', FALSE)
        """), {"id": str(uuid.uuid4()), "org_a": org_a_id, "doc_a1": doc_a1_id})
    db_session.rollback()

    # 2. Confidence must be in [0, 1]
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO findings (
                id, organization_id, constitution_id, document_id, version_id, job_id,
                category, severity, confidence, flagged_snippet, explanation,
                evidence_type, rule_id, cited_code, source
            ) VALUES (
                :id, :org_a, :const_a, :doc_a1, :ver_a1, :job_a,
                'TONE', 'LOW', 1.500, 'snip', 'bad', 'RULE', :rule_a, 'TONE-01', 'LIVE_LLM'
            )
        """), {
            "id": str(uuid.uuid4()), "org_a": org_a_id, "const_a": const_a_id,
            "doc_a1": doc_a1_id, "ver_a1": ver_a1_id, "job_a": job_a1_id, "rule_a": rule_a_id
        })
    db_session.rollback()

    # 3. Comment cannot reference finding from another document/version
    with pytest.raises(IntegrityError):
        db_session.execute(text("""
            INSERT INTO comments (id, organization_id, document_id, version_id, finding_id, user_id, content)
            VALUES (:id, :org_a, :doc_a2, :ver_a2, :finding_a1, :user_a, 'Mismatched finding comment')
        """), {
            "id": str(uuid.uuid4()), "org_a": org_a_id, "doc_a2": doc_a2_id,
            "ver_a2": ver_a2_id, "finding_a1": finding_a1_id, "user_a": user_a_id
        })
    db_session.rollback()

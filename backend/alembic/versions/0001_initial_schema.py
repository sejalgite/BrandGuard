"""Initial Schema with PostgreSQL 18, pgvector, Composite Tenancy and Immutability Triggers

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-06 00:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')

    # 2. Schema SQL execution with full constraints, triggers, and immutability guards
    op.execute("""
    -- Custom Enums
    DO $$ BEGIN
        CREATE TYPE user_role AS ENUM (
            'ADMIN', 'CONTENT_CREATOR', 'EXTERNAL_AGENCY', 
            'REVIEWER', 'BRAND_MANAGER', 'LEGAL_REVIEWER', 'LEADERSHIP'
        );
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE rule_category AS ENUM (
            'TONE_VOICE', 'WRITING_STYLE', 'MESSAGING_PILLAR', 'VISUAL', 'ACCESSIBILITY'
        );
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE entity_status AS ENUM ('PENDING_APPROVAL', 'ACTIVE', 'REJECTED', 'ARCHIVED');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE document_lifecycle_status AS ENUM ('IN_PROGRESS', 'APPROVED', 'ARCHIVED');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE version_workflow_status AS ENUM (
            'DRAFT', 'ANALYZING', 'CHANGES_REQUIRED', 
            'REVIEW_PENDING', 'APPROVED', 'REJECTED'
        );
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE detection_category AS ENUM (
            'TONE', 'TERMINOLOGY', 'MESSAGING', 'VISUAL', 'ACCESSIBILITY', 'CLAIMS'
        );
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE finding_status AS ENUM ('OPEN', 'ACCEPTED', 'EDITED', 'DISPUTED', 'DISMISSED');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE finding_source AS ENUM ('DETERMINISTIC_ENGINE', 'LIVE_LLM');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE evidence_entity_type AS ENUM ('RULE', 'FACT', 'TERM', 'ASSET');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    -- Tables
    CREATE TABLE IF NOT EXISTS organizations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(100) UNIQUE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role user_role NOT NULL DEFAULT 'CONTENT_CREATOR',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        CONSTRAINT uq_users_org_id UNIQUE (organization_id, id),
        CONSTRAINT uq_org_email UNIQUE (organization_id, email)
    );

    CREATE TABLE IF NOT EXISTS brand_constitutions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        version VARCHAR(50) DEFAULT '1.0',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        CONSTRAINT uq_constitutions_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS brand_rules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        constitution_id UUID NOT NULL,
        rule_code VARCHAR(50) NOT NULL,
        category rule_category NOT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        examples_positive TEXT[],
        examples_negative TEXT[],
        embedding vector(384),
        status entity_status NOT NULL DEFAULT 'ACTIVE',
        approved_by UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, constitution_id) REFERENCES brand_constitutions(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_rules_org_const_id UNIQUE (organization_id, constitution_id, id),
        CONSTRAINT uq_constitution_rule_code UNIQUE (constitution_id, rule_code)
    );

    CREATE TABLE IF NOT EXISTS fact_registry (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        constitution_id UUID NOT NULL,
        fact_code VARCHAR(50) NOT NULL,
        claim_type VARCHAR(100) NOT NULL,
        statement TEXT NOT NULL,
        numerical_value NUMERIC,
        unit VARCHAR(50),
        source_reference VARCHAR(255) NOT NULL,
        fact_owner VARCHAR(255) NOT NULL,
        expiry_date DATE NOT NULL,
        embedding vector(384),
        status entity_status NOT NULL DEFAULT 'ACTIVE',
        approved_by UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, constitution_id) REFERENCES brand_constitutions(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_facts_org_const_id UNIQUE (organization_id, constitution_id, id),
        CONSTRAINT uq_constitution_fact_code UNIQUE (constitution_id, fact_code)
    );

    CREATE TABLE IF NOT EXISTS term_bank (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        constitution_id UUID NOT NULL,
        term_code VARCHAR(50) NOT NULL,
        prohibited_term VARCHAR(255) NOT NULL,
        preferred_term VARCHAR(255) NOT NULL,
        usage_context TEXT,
        is_case_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
        status entity_status NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, constitution_id) REFERENCES brand_constitutions(organization_id, id) ON DELETE CASCADE,
        CONSTRAINT uq_terms_org_const_id UNIQUE (organization_id, constitution_id, id),
        CONSTRAINT uq_constitution_term_code UNIQUE (constitution_id, term_code)
    );

    CREATE TABLE IF NOT EXISTS brand_assets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        constitution_id UUID NOT NULL,
        asset_code VARCHAR(50) NOT NULL,
        asset_type VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        specifications JSONB NOT NULL,
        file_path VARCHAR(500),
        status entity_status NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, constitution_id) REFERENCES brand_constitutions(organization_id, id) ON DELETE CASCADE,
        CONSTRAINT uq_assets_org_const_id UNIQUE (organization_id, constitution_id, id),
        CONSTRAINT uq_constitution_asset_code UNIQUE (constitution_id, asset_code)
    );

    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        creator_id UUID NOT NULL,
        title VARCHAR(255) NOT NULL,
        content_type VARCHAR(50) NOT NULL,
        lifecycle_status document_lifecycle_status NOT NULL DEFAULT 'IN_PROGRESS',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, creator_id) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_documents_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS document_versions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        document_id UUID NOT NULL,
        version_number INTEGER NOT NULL,
        raw_content TEXT,
        file_path VARCHAR(500),
        extracted_text TEXT,
        intent_lock JSONB,
        brand_health_score NUMERIC(5, 2),
        word_count INTEGER NOT NULL DEFAULT 0,
        version_status version_workflow_status NOT NULL DEFAULT 'DRAFT',
        is_locked BOOLEAN NOT NULL DEFAULT FALSE,
        approved_at TIMESTAMP WITH TIME ZONE,
        approved_by UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, document_id) REFERENCES documents(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, approved_by) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_versions_org_id UNIQUE (organization_id, id),
        CONSTRAINT uq_versions_org_doc_id UNIQUE (organization_id, document_id, id),
        CONSTRAINT uq_doc_version UNIQUE (document_id, version_number),
        CONSTRAINT chk_approved_is_locked CHECK (version_status != 'APPROVED' OR is_locked = TRUE),
        CONSTRAINT chk_version_brand_score CHECK (brand_health_score IS NULL OR (brand_health_score >= 0.00 AND brand_health_score <= 100.00)),
        CONSTRAINT chk_version_word_count CHECK (word_count >= 0)
    );

    -- Trigger for version immutability
    CREATE OR REPLACE FUNCTION prevent_locked_version_mutation()
    RETURNS TRIGGER AS $func$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF OLD.is_locked = TRUE THEN
                RAISE EXCEPTION 'Database Guard: Document Version % is locked and immutable. Update rejected.', OLD.id;
            END IF;
            RETURN NEW;
        ELSIF TG_OP = 'DELETE' THEN
            IF OLD.is_locked = TRUE THEN
                RAISE EXCEPTION 'Database Guard: Document Version % is locked and immutable. Deletion rejected.', OLD.id;
            END IF;
            RETURN OLD;
        END IF;
        RETURN NULL;
    END;
    $func$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_prevent_locked_version_mutation ON document_versions;
    CREATE TRIGGER trg_prevent_locked_version_mutation
    BEFORE UPDATE OR DELETE ON document_versions
    FOR EACH ROW
    EXECUTE FUNCTION prevent_locked_version_mutation();

    CREATE TABLE IF NOT EXISTS review_jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        document_id UUID NOT NULL,
        version_id UUID NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'RUNNING',
        started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        completed_at TIMESTAMP WITH TIME ZONE,
        FOREIGN KEY (organization_id, document_id, version_id) 
            REFERENCES document_versions(organization_id, document_id, id) ON DELETE CASCADE,
        CONSTRAINT uq_jobs_org_id UNIQUE (organization_id, id),
        CONSTRAINT uq_jobs_org_doc_ver_id UNIQUE (organization_id, document_id, version_id, id)
    );

    CREATE TABLE IF NOT EXISTS findings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        constitution_id UUID NOT NULL,
        document_id UUID NOT NULL,
        version_id UUID NOT NULL,
        job_id UUID NOT NULL,
        category detection_category NOT NULL,
        severity severity_level NOT NULL,
        confidence NUMERIC(4, 3) NOT NULL,
        flagged_snippet TEXT NOT NULL,
        char_offset_start INTEGER,
        char_offset_end INTEGER,
        explanation TEXT NOT NULL,
        
        evidence_type evidence_entity_type NOT NULL,
        rule_id UUID,
        fact_id UUID,
        term_id UUID,
        asset_id UUID,
        cited_code VARCHAR(50) NOT NULL,
        
        source finding_source NOT NULL,
        status finding_status NOT NULL DEFAULT 'OPEN',
        verified_by_gate BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

        FOREIGN KEY (organization_id, job_id) REFERENCES review_jobs(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, document_id, version_id) REFERENCES document_versions(organization_id, document_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, constitution_id) REFERENCES brand_constitutions(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, constitution_id, rule_id) 
            REFERENCES brand_rules(organization_id, constitution_id, id) ON DELETE RESTRICT,
        FOREIGN KEY (organization_id, constitution_id, fact_id) 
            REFERENCES fact_registry(organization_id, constitution_id, id) ON DELETE RESTRICT,
        FOREIGN KEY (organization_id, constitution_id, term_id) 
            REFERENCES term_bank(organization_id, constitution_id, id) ON DELETE RESTRICT,
        FOREIGN KEY (organization_id, constitution_id, asset_id) 
            REFERENCES brand_assets(organization_id, constitution_id, id) ON DELETE RESTRICT,

        CONSTRAINT chk_exactly_one_evidence CHECK (
            ((rule_id IS NOT NULL)::int + 
             (fact_id IS NOT NULL)::int + 
             (term_id IS NOT NULL)::int + 
             (asset_id IS NOT NULL)::int) = 1
        ),
        CONSTRAINT chk_evidence_type_match CHECK (
            (evidence_type = 'RULE' AND rule_id IS NOT NULL) OR
            (evidence_type = 'FACT' AND fact_id IS NOT NULL) OR
            (evidence_type = 'TERM' AND term_id IS NOT NULL) OR
            (evidence_type = 'ASSET' AND asset_id IS NOT NULL)
        ),
        CONSTRAINT chk_finding_confidence CHECK (confidence >= 0.000 AND confidence <= 1.000),
        CONSTRAINT chk_finding_char_offsets CHECK (
            char_offset_start IS NULL OR (char_offset_start >= 0 AND (char_offset_end IS NULL OR char_offset_end >= char_offset_start))
        ),
        CONSTRAINT uq_findings_org_id UNIQUE (organization_id, id),
        CONSTRAINT uq_findings_org_doc_ver_id UNIQUE (organization_id, document_id, version_id, id)
    );

    CREATE TABLE IF NOT EXISTS suggested_corrections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        finding_id UUID NOT NULL,
        option_label VARCHAR(50) NOT NULL,
        suggested_text TEXT NOT NULL,
        intent_preserved BOOLEAN NOT NULL DEFAULT TRUE,
        routing_action VARCHAR(100) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, finding_id) REFERENCES findings(organization_id, id) ON DELETE CASCADE,
        CONSTRAINT uq_corrections_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS disputes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        finding_id UUID NOT NULL,
        user_id UUID NOT NULL,
        justification TEXT NOT NULL,
        resolved_by UUID,
        resolution_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, finding_id) REFERENCES findings(organization_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        FOREIGN KEY (organization_id, resolved_by) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_disputes_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS review_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        document_id UUID NOT NULL,
        version_id UUID NOT NULL,
        assigned_user_id UUID NOT NULL,
        assigned_by UUID NOT NULL,
        role_required user_role NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, document_id, version_id) 
            REFERENCES document_versions(organization_id, document_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, assigned_user_id) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        FOREIGN KEY (organization_id, assigned_by) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_assignments_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL,
        document_id UUID NOT NULL,
        version_id UUID NOT NULL,
        finding_id UUID,
        user_id UUID NOT NULL,
        parent_comment_id UUID,
        content TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, document_id, version_id) 
            REFERENCES document_versions(organization_id, document_id, id) ON DELETE CASCADE,
        -- Column-specific nullification on finding deletion
        FOREIGN KEY (organization_id, document_id, version_id, finding_id) 
            REFERENCES findings(organization_id, document_id, version_id, id) ON DELETE CASCADE,
        FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id) ON DELETE RESTRICT,
        CONSTRAINT uq_comments_org_doc_ver_id UNIQUE (organization_id, document_id, version_id, id),
        FOREIGN KEY (organization_id, document_id, version_id, parent_comment_id) 
            REFERENCES comments(organization_id, document_id, version_id, id) ON DELETE CASCADE,
        CONSTRAINT uq_comments_org_id UNIQUE (organization_id, id)
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        actor_id UUID,
        action VARCHAR(100) NOT NULL,
        target_entity VARCHAR(100) NOT NULL,
        target_id UUID NOT NULL,
        version_number INTEGER,
        details JSONB,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, actor_id) REFERENCES users(organization_id, id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS ai_disclosure_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        review_job_id UUID NOT NULL,
        model_name VARCHAR(100) NOT NULL,
        prompt_type VARCHAR(100) NOT NULL,
        tokens_prompt INTEGER,
        tokens_completion INTEGER,
        redacted_preview_hash VARCHAR(64) NOT NULL,
        latency_ms INTEGER NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        FOREIGN KEY (organization_id, review_job_id) REFERENCES review_jobs(organization_id, id) ON DELETE CASCADE
    );

    -- Trigger for audit log immutability
    CREATE OR REPLACE FUNCTION prevent_audit_mutation()
    RETURNS TRIGGER AS $func$
    BEGIN
        RAISE EXCEPTION 'Database Guard: Table % is strictly append-only. Modifying or deleting audit history is prohibited.', TG_TABLE_NAME;
    END;
    $func$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_prevent_audit_log_mutation ON audit_logs;
    CREATE TRIGGER trg_prevent_audit_log_mutation
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_mutation();

    DROP TRIGGER IF EXISTS trg_prevent_ai_log_mutation ON ai_disclosure_logs;
    CREATE TRIGGER trg_prevent_ai_log_mutation
    BEFORE UPDATE OR DELETE ON ai_disclosure_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_mutation();

    -- Vector indexes
    CREATE INDEX IF NOT EXISTS idx_rules_hnsw ON brand_rules USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_facts_hnsw ON fact_registry USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_findings_job ON findings (organization_id, job_id);
    CREATE INDEX IF NOT EXISTS idx_audit_org_time ON audit_logs (organization_id, timestamp DESC);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS ai_disclosure_logs CASCADE;
    DROP TABLE IF EXISTS audit_logs CASCADE;
    DROP TABLE IF EXISTS comments CASCADE;
    DROP TABLE IF EXISTS review_assignments CASCADE;
    DROP TABLE IF EXISTS disputes CASCADE;
    DROP TABLE IF EXISTS suggested_corrections CASCADE;
    DROP TABLE IF EXISTS findings CASCADE;
    DROP TABLE IF EXISTS review_jobs CASCADE;
    DROP TABLE IF EXISTS document_versions CASCADE;
    DROP TABLE IF EXISTS documents CASCADE;
    DROP TABLE IF EXISTS brand_assets CASCADE;
    DROP TABLE IF EXISTS term_bank CASCADE;
    DROP TABLE IF EXISTS fact_registry CASCADE;
    DROP TABLE IF EXISTS brand_rules CASCADE;
    DROP TABLE IF EXISTS brand_constitutions CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    DROP TABLE IF EXISTS organizations CASCADE;
    DROP TYPE IF EXISTS evidence_entity_type CASCADE;
    DROP TYPE IF EXISTS finding_source CASCADE;
    DROP TYPE IF EXISTS finding_status CASCADE;
    DROP TYPE IF EXISTS severity_level CASCADE;
    DROP TYPE IF EXISTS detection_category CASCADE;
    DROP TYPE IF EXISTS version_workflow_status CASCADE;
    DROP TYPE IF EXISTS document_lifecycle_status CASCADE;
    DROP TYPE IF EXISTS entity_status CASCADE;
    DROP TYPE IF EXISTS rule_category CASCADE;
    DROP TYPE IF EXISTS user_role CASCADE;
    """)


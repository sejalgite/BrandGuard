"""Human Review, Approval & Governance Workflow

Revision ID: 0006_review_governance
Revises: 0005_analysis_engine
Create Date: 2026-11-06 21:20:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0006_review_governance'
down_revision = '0005_analysis_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create Enums if they do not exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'review_workflow_status') THEN
                CREATE TYPE review_workflow_status AS ENUM (
                    'DRAFT',
                    'SUBMITTED',
                    'UNDER_REVIEW',
                    'CHANGES_REQUESTED',
                    'RESUBMITTED',
                    'PENDING_BRAND_APPROVAL',
                    'PENDING_LEGAL_APPROVAL',
                    'APPROVED',
                    'REJECTED',
                    'WITHDRAWN'
                );
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'finding_decision_type') THEN
                CREATE TYPE finding_decision_type AS ENUM (
                    'ACCEPTED',
                    'DISMISSED',
                    'DISPUTED',
                    'RESOLVED',
                    'CORRECTION_REQUESTED'
                );
            END IF;
        END$$;
    """)

    # 2. Create reviews table
    op.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            document_id UUID NOT NULL,
            version_id UUID NOT NULL,
            job_id UUID,
            creator_id UUID NOT NULL,
            assigned_reviewer_id UUID,
            legal_reviewer_id UUID,
            status review_workflow_status NOT NULL DEFAULT 'DRAFT',
            priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
            due_date TIMESTAMP WITH TIME ZONE,
            legal_review_required BOOLEAN NOT NULL DEFAULT FALSE,
            legal_status VARCHAR(50) NOT NULL DEFAULT 'NOT_REQUIRED',
            final_decision_by UUID,
            final_decision_at TIMESTAMP WITH TIME ZONE,
            decision_notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            FOREIGN KEY (organization_id, document_id, version_id) 
                REFERENCES document_versions(organization_id, document_id, id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id, creator_id) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (organization_id, assigned_reviewer_id) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (organization_id, legal_reviewer_id) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (organization_id, final_decision_by) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_reviews_org_id UNIQUE (organization_id, id),
            CONSTRAINT uq_reviews_org_doc_ver_id UNIQUE (organization_id, document_id, version_id, id)
        );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_org_status ON reviews(organization_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_assigned_reviewer ON reviews(organization_id, assigned_reviewer_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_doc_version ON reviews(organization_id, document_id, version_id);")

    # 3. Create review_history table
    op.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL,
            review_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            from_status VARCHAR(50),
            to_status VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            FOREIGN KEY (organization_id, review_id) 
                REFERENCES reviews(organization_id, id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id, actor_id) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_review_history_org_id UNIQUE (organization_id, id)
        );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_review_history_review_id ON review_history(organization_id, review_id, created_at);")

    # 4. Create finding_decisions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS finding_decisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL,
            review_id UUID NOT NULL,
            finding_id UUID NOT NULL,
            decided_by UUID NOT NULL,
            decision finding_decision_type NOT NULL,
            reason TEXT,
            suggested_correction TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            FOREIGN KEY (organization_id, review_id) 
                REFERENCES reviews(organization_id, id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id, finding_id) 
                REFERENCES findings(organization_id, id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id, decided_by) 
                REFERENCES users(organization_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_finding_decisions_org_id UNIQUE (organization_id, id)
        );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_finding_decisions_finding ON finding_decisions(organization_id, finding_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_finding_decisions_review ON finding_decisions(organization_id, review_id);")

    # 5. Create notifications table
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL,
            recipient_id UUID NOT NULL,
            actor_id UUID,
            title VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            notification_type VARCHAR(50) NOT NULL,
            resource_type VARCHAR(50),
            resource_id UUID,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            FOREIGN KEY (organization_id, recipient_id) 
                REFERENCES users(organization_id, id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id, actor_id) 
                REFERENCES users(organization_id, id) ON DELETE SET NULL,
            CONSTRAINT uq_notifications_org_id UNIQUE (organization_id, id)
        );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_recipient_unread ON notifications(organization_id, recipient_id, is_read);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications(organization_id, created_at);")

    # 6. Add review_id to comments table
    op.execute("ALTER TABLE comments ADD COLUMN IF NOT EXISTS review_id UUID;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_comments_review_id ON comments(organization_id, review_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications CASCADE;")
    op.execute("DROP TABLE IF EXISTS finding_decisions CASCADE;")
    op.execute("DROP TABLE IF EXISTS review_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS reviews CASCADE;")
    op.execute("DROP TYPE IF EXISTS finding_decision_type CASCADE;")
    op.execute("DROP TYPE IF EXISTS review_workflow_status CASCADE;")
    op.execute("ALTER TABLE comments DROP COLUMN IF EXISTS review_id;")


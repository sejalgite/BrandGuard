"""Evaluation, Reliability & Intelligence

Revision ID: 0007_evaluation_intelligence
Revises: 0006_review_governance
Create Date: 2026-11-06 22:50:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0007_evaluation_intelligence'
down_revision = '0006_review_governance'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create evaluation_datasets table
    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_datasets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            dataset_type VARCHAR(50) NOT NULL DEFAULT 'BENCHMARK',
            version VARCHAR(50) NOT NULL DEFAULT '1.0',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT uq_evaluation_datasets_org_name_ver UNIQUE (organization_id, name, version)
        );
        CREATE INDEX IF NOT EXISTS ix_evaluation_datasets_org ON evaluation_datasets(organization_id);
    """)

    # 2. Create evaluation_test_cases table
    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_test_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            dataset_id UUID NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
            test_code VARCHAR(100) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content_type VARCHAR(50) NOT NULL DEFAULT 'TEXT',
            input_content TEXT NOT NULL,
            content_metadata JSONB DEFAULT '{}',
            expected_findings JSONB NOT NULL DEFAULT '[]',
            expected_compliant BOOLEAN NOT NULL DEFAULT FALSE,
            is_ambiguous BOOLEAN NOT NULL DEFAULT FALSE,
            target_category VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            CONSTRAINT uq_evaluation_test_cases_code UNIQUE (organization_id, dataset_id, test_code)
        );
        CREATE INDEX IF NOT EXISTS ix_evaluation_test_cases_dataset ON evaluation_test_cases(dataset_id);
        CREATE INDEX IF NOT EXISTS ix_evaluation_test_cases_org ON evaluation_test_cases(organization_id);
    """)

    # 3. Create evaluation_runs table
    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            dataset_id UUID NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
            engine_version VARCHAR(50) NOT NULL DEFAULT '1.0.0-phase7',
            run_type VARCHAR(50) NOT NULL DEFAULT 'BENCHMARK',
            total_cases INTEGER NOT NULL DEFAULT 0,
            overall_precision FLOAT NOT NULL DEFAULT 0.0,
            overall_recall FLOAT NOT NULL DEFAULT 0.0,
            overall_f1 FLOAT NOT NULL DEFAULT 0.0,
            overall_accuracy FLOAT NOT NULL DEFAULT 0.0,
            category_metrics JSONB NOT NULL DEFAULT '{}',
            case_results JSONB NOT NULL DEFAULT '[]',
            triggered_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_evaluation_runs_org ON evaluation_runs(organization_id);
        CREATE INDEX IF NOT EXISTS ix_evaluation_runs_dataset ON evaluation_runs(dataset_id);
        CREATE INDEX IF NOT EXISTS ix_evaluation_runs_created ON evaluation_runs(created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_runs CASCADE;")
    op.execute("DROP TABLE IF EXISTS evaluation_test_cases CASCADE;")
    op.execute("DROP TABLE IF EXISTS evaluation_datasets CASCADE;")

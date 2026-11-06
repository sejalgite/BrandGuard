"""Add analysis run execution metadata, segment references, and query indexes

Revision ID: 0005_analysis_engine
Revises: 0004_document_extraction
Create Date: 2026-11-06 15:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005_analysis_engine'
down_revision: Union[str, None] = '0004_document_extraction'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update Enums with IF NOT EXISTS in PostgreSQL
    op.execute("ALTER TYPE severity_level ADD VALUE IF NOT EXISTS 'INFO';")
    op.execute("ALTER TYPE finding_status ADD VALUE IF NOT EXISTS 'NEEDS_REVIEW';")

    # 2. Add columns to review_jobs
    op.add_column('review_jobs', sa.Column('trigger_type', sa.String(length=50), server_default='MANUAL', nullable=False))
    op.add_column('review_jobs', sa.Column('total_findings', sa.Integer(), server_default='0', nullable=False))
    op.add_column('review_jobs', sa.Column('categories_analyzed', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('review_jobs', sa.Column('execution_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.add_column('review_jobs', sa.Column('error_message', sa.Text(), nullable=True))

    # 3. Add columns to findings
    op.add_column('findings', sa.Column('segment_id', sa.String(length=100), nullable=True))
    op.add_column('findings', sa.Column('suggested_correction', sa.Text(), nullable=True))

    # 4. Create performance and filtering indexes
    op.create_index('idx_findings_org_doc_ver', 'findings', ['organization_id', 'document_id', 'version_id'], unique=False)
    op.create_index('idx_findings_category', 'findings', ['organization_id', 'category'], unique=False)
    op.create_index('idx_findings_severity', 'findings', ['organization_id', 'severity'], unique=False)
    op.create_index('idx_findings_status', 'findings', ['organization_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_findings_status', table_name='findings')
    op.drop_index('idx_findings_severity', table_name='findings')
    op.drop_index('idx_findings_category', table_name='findings')
    op.drop_index('idx_findings_org_doc_ver', table_name='findings')

    op.drop_column('findings', 'suggested_correction')
    op.drop_column('findings', 'segment_id')

    op.drop_column('review_jobs', 'error_message')
    op.drop_column('review_jobs', 'execution_metadata')
    op.drop_column('review_jobs', 'categories_analyzed')
    op.drop_column('review_jobs', 'total_findings')
    op.drop_column('review_jobs', 'trigger_type')


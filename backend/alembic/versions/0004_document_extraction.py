"""Add extraction metadata and structured content to document_versions

Revision ID: 0004_document_extraction
Revises: 0003_draft_expired_status
Create Date: 2026-11-06 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004_document_extraction'
down_revision: Union[str, None] = '0003_draft_expired_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_versions', sa.Column('original_filename', sa.String(length=255), nullable=True))
    op.add_column('document_versions', sa.Column('file_size_bytes', sa.Integer(), nullable=True))
    op.add_column('document_versions', sa.Column('mime_type', sa.String(length=100), nullable=True))
    op.add_column('document_versions', sa.Column('extraction_status', sa.String(length=50), server_default='PENDING', nullable=False))
    op.add_column('document_versions', sa.Column('extraction_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('document_versions', sa.Column('structured_content', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('document_versions', sa.Column('character_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('document_versions', 'character_count')
    op.drop_column('document_versions', 'structured_content')
    op.drop_column('document_versions', 'extraction_metadata')
    op.drop_column('document_versions', 'extraction_status')
    op.drop_column('document_versions', 'mime_type')
    op.drop_column('document_versions', 'file_size_bytes')
    op.drop_column('document_versions', 'original_filename')


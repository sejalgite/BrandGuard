"""Add DRAFT and EXPIRED to entity_status enum

Revision ID: 0003_draft_expired_status
Revises: 0002_add_revoked_tokens
Create Date: 2026-11-06 11:50:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = '0003_draft_expired_status'
down_revision: Union[str, None] = '0002_add_revoked_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE entity_status ADD VALUE IF NOT EXISTS 'DRAFT' BEFORE 'PENDING_APPROVAL';")
        op.execute("ALTER TYPE entity_status ADD VALUE IF NOT EXISTS 'EXPIRED';")


def downgrade() -> None:
    pass


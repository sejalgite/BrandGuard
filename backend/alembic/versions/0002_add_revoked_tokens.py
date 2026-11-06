"""Add revoked_tokens table for server-side JWT revocation

Revision ID: 0002_add_revoked_tokens
Revises: 0001_initial_schema
Create Date: 2026-11-06 11:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002_add_revoked_tokens'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS revoked_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        token_jti VARCHAR(64) NOT NULL UNIQUE,
        user_id UUID NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT fk_revoked_tokens_user FOREIGN KEY (organization_id, user_id)
            REFERENCES users(organization_id, id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti ON revoked_tokens(token_jti);
    CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS revoked_tokens CASCADE;")


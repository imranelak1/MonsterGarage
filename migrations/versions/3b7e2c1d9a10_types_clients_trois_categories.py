"""types clients trois categories

Revision ID: 3b7e2c1d9a10
Revises: 38f0f7f52fa5
Create Date: 2026-05-01
"""

from alembic import op


revision = "3b7e2c1d9a10"
down_revision = "38f0f7f52fa5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE clients SET type = 'particulier' WHERE type = 'entreprise'")


def downgrade():
    pass

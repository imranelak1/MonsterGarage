"""assurance dossier

Revision ID: b4e72df36c91
Revises: 8a41c2b9d7e3
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


revision = "b4e72df36c91"
down_revision = "8a41c2b9d7e3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("dossiers_reparation") as batch_op:
        batch_op.add_column(sa.Column("assurance_nom", sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table("dossiers_reparation") as batch_op:
        batch_op.drop_column("assurance_nom")

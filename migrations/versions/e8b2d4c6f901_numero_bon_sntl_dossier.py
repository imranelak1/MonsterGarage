"""numero bon sntl dossier

Revision ID: e8b2d4c6f901
Revises: d7f3c2a1b9e4
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "e8b2d4c6f901"
down_revision = "d7f3c2a1b9e4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("dossiers_reparation") as batch_op:
        batch_op.add_column(sa.Column("numero_bon_sntl", sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table("dossiers_reparation") as batch_op:
        batch_op.drop_column("numero_bon_sntl")

"""etat piece ligne devis

Revision ID: 48cf97a21a2d
Revises: 3b7e2c1d9a10
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "48cf97a21a2d"
down_revision = "3b7e2c1d9a10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lignes_devis_reparation") as batch_op:
        batch_op.add_column(
            sa.Column(
                "etat_piece",
                sa.Enum("neuf", "occasion", name="etat_piece_devis"),
                nullable=False,
                server_default="neuf",
            )
        )


def downgrade():
    with op.batch_alter_table("lignes_devis_reparation") as batch_op:
        batch_op.drop_column("etat_piece")

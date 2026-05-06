"""montant regle factures

Revision ID: d7f3c2a1b9e4
Revises: c9d4e7f2a8b1
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa


revision = "d7f3c2a1b9e4"
down_revision = "c9d4e7f2a8b1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("factures_reparation") as batch_op:
        batch_op.add_column(
            sa.Column(
                "montant_regle",
                sa.Numeric(precision=12, scale=2),
                nullable=False,
                server_default="0",
            )
        )

    with op.batch_alter_table("factures_reparation") as batch_op:
        batch_op.alter_column("montant_regle", server_default=None)


def downgrade():
    with op.batch_alter_table("factures_reparation") as batch_op:
        batch_op.drop_column("montant_regle")

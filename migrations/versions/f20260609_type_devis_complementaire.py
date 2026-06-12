"""type devis complementaire

Revision ID: f20260609
Revises: e20260606
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa


revision = "f20260609"
down_revision = "e20260606"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TABLE IF EXISTS _alembic_tmp_devis_reparation")

    columns = {column["name"] for column in sa.inspect(bind).get_columns("devis_reparation")}
    if "est_complementaire" not in columns:
        op.add_column(
            "devis_reparation",
            sa.Column("est_complementaire", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    op.execute(
        """
        UPDATE devis_reparation
        SET est_complementaire = 1
        WHERE EXISTS (
            SELECT 1
            FROM devis_reparation AS precedent
            WHERE precedent.dossier_id = devis_reparation.dossier_id
              AND precedent.version < devis_reparation.version
              AND precedent.statut = 'approved'
        )
        """
    )

    if bind.dialect.name != "sqlite":
        with op.batch_alter_table("devis_reparation") as batch_op:
            batch_op.alter_column("est_complementaire", server_default=None)


def downgrade():
    with op.batch_alter_table("devis_reparation") as batch_op:
        batch_op.drop_column("est_complementaire")

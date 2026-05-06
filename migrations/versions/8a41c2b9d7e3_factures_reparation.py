"""factures reparation

Revision ID: 8a41c2b9d7e3
Revises: 48cf97a21a2d
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


revision = "8a41c2b9d7e3"
down_revision = "48cf97a21a2d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "factures_reparation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=30), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("devis_id", sa.Integer(), nullable=False),
        sa.Column(
            "statut",
            sa.Enum("emise", "livree", "reglee", "annulee", name="statut_facture_reparation"),
            nullable=False,
        ),
        sa.Column("montant_ht", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("montant_tva", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("montant_ttc", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "mode_reglement",
            sa.Enum("especes", "cheque", "virement", "carte", "autre", name="mode_reglement_facture"),
            nullable=True,
        ),
        sa.Column("reference_reglement", sa.String(length=100), nullable=True),
        sa.Column("livree_le", sa.DateTime(), nullable=True),
        sa.Column("reglee_le", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["utilisateurs.id"]),
        sa.ForeignKeyConstraint(["devis_id"], ["devis_reparation.id"]),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers_reparation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dossier_id"),
    )
    with op.batch_alter_table("factures_reparation") as batch_op:
        batch_op.create_index(batch_op.f("ix_factures_reparation_devis_id"), ["devis_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_factures_reparation_dossier_id"), ["dossier_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_factures_reparation_numero"), ["numero"], unique=True)
        batch_op.create_index(batch_op.f("ix_factures_reparation_statut"), ["statut"], unique=False)


def downgrade():
    with op.batch_alter_table("factures_reparation") as batch_op:
        batch_op.drop_index(batch_op.f("ix_factures_reparation_statut"))
        batch_op.drop_index(batch_op.f("ix_factures_reparation_numero"))
        batch_op.drop_index(batch_op.f("ix_factures_reparation_dossier_id"))
        batch_op.drop_index(batch_op.f("ix_factures_reparation_devis_id"))

    op.drop_table("factures_reparation")

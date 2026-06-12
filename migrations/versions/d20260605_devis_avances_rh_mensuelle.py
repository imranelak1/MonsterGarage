"""devis avances client rh mensuelle

Revision ID: d20260605
Revises: ca20260530
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa


revision = "d20260605"
down_revision = "ca20260530"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lignes_devis_reparation") as batch_op:
        batch_op.add_column(sa.Column("type_ligne", sa.String(length=20), nullable=False, server_default="piece"))
        batch_op.add_column(sa.Column("etat_piece_autre", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("type_mo", sa.String(length=40), nullable=True))

    op.execute(
        """
        UPDATE lignes_devis_reparation
        SET type_ligne = 'main_oeuvre', etat_piece = 'mo'
        WHERE lower(designation) LIKE '%main%d%oeuvre%'
           OR lower(designation) LIKE '%main%oeuvre%'
        """
    )

    with op.batch_alter_table("employes") as batch_op:
        batch_op.add_column(sa.Column("salaire_mensuel", sa.Numeric(precision=10, scale=2), nullable=True))

    op.create_table(
        "avances_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("montant", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("mode_reglement", sa.String(length=20), nullable=False, server_default="especes"),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["utilisateurs.id"]),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers_reparation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_avances_clients_dossier_id"), "avances_clients", ["dossier_id"], unique=False)

    with op.batch_alter_table("lignes_devis_reparation") as batch_op:
        batch_op.alter_column("type_ligne", server_default=None)
    with op.batch_alter_table("avances_clients") as batch_op:
        batch_op.alter_column("mode_reglement", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_avances_clients_dossier_id"), table_name="avances_clients")
    op.drop_table("avances_clients")

    with op.batch_alter_table("employes") as batch_op:
        batch_op.drop_column("salaire_mensuel")

    with op.batch_alter_table("lignes_devis_reparation") as batch_op:
        batch_op.drop_column("type_mo")
        batch_op.drop_column("etat_piece_autre")
        batch_op.drop_column("type_ligne")

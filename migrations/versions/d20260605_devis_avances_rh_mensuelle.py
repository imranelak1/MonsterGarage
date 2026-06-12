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
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("PRAGMA busy_timeout=60000")

    inspector = sa.inspect(bind)

    lignes_columns = _column_names(inspector, "lignes_devis_reparation")
    lignes_columns_to_add = []
    if "type_ligne" not in lignes_columns:
        lignes_columns_to_add.append(sa.Column("type_ligne", sa.String(length=20), nullable=False, server_default="piece"))
    if "etat_piece_autre" not in lignes_columns:
        lignes_columns_to_add.append(sa.Column("etat_piece_autre", sa.String(length=80), nullable=True))
    if "type_mo" not in lignes_columns:
        lignes_columns_to_add.append(sa.Column("type_mo", sa.String(length=40), nullable=True))

    if lignes_columns_to_add:
        with op.batch_alter_table("lignes_devis_reparation") as batch_op:
            for column in lignes_columns_to_add:
                batch_op.add_column(column)

    op.execute(
        """
        UPDATE lignes_devis_reparation
        SET type_ligne = 'main_oeuvre', etat_piece = 'mo'
        WHERE lower(designation) LIKE '%main%d%oeuvre%'
           OR lower(designation) LIKE '%main%oeuvre%'
        """
    )

    employes_columns = _column_names(sa.inspect(bind), "employes")
    if "salaire_mensuel" not in employes_columns:
        with op.batch_alter_table("employes") as batch_op:
            batch_op.add_column(sa.Column("salaire_mensuel", sa.Numeric(precision=10, scale=2), nullable=True))

    inspector = sa.inspect(bind)
    if "avances_clients" not in inspector.get_table_names():
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

    inspector = sa.inspect(bind)
    avances_indexes = {index["name"] for index in inspector.get_indexes("avances_clients")}
    if op.f("ix_avances_clients_dossier_id") not in avances_indexes:
        op.create_index(op.f("ix_avances_clients_dossier_id"), "avances_clients", ["dossier_id"], unique=False)

    if bind.dialect.name != "sqlite":
        with op.batch_alter_table("lignes_devis_reparation") as batch_op:
            batch_op.alter_column("type_ligne", server_default=None)
        with op.batch_alter_table("avances_clients") as batch_op:
            batch_op.alter_column("mode_reglement", server_default=None)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "avances_clients" in inspector.get_table_names():
        avances_indexes = {index["name"] for index in inspector.get_indexes("avances_clients")}
        if op.f("ix_avances_clients_dossier_id") in avances_indexes:
            op.drop_index(op.f("ix_avances_clients_dossier_id"), table_name="avances_clients")
        op.drop_table("avances_clients")

    employes_columns = _column_names(sa.inspect(bind), "employes")
    if "salaire_mensuel" in employes_columns:
        with op.batch_alter_table("employes") as batch_op:
            batch_op.drop_column("salaire_mensuel")

    lignes_columns = _column_names(sa.inspect(bind), "lignes_devis_reparation")
    lignes_columns_to_drop = [
        column for column in ("type_mo", "etat_piece_autre", "type_ligne") if column in lignes_columns
    ]
    if lignes_columns_to_drop:
        with op.batch_alter_table("lignes_devis_reparation") as batch_op:
            for column in lignes_columns_to_drop:
                batch_op.drop_column(column)


def _column_names(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}

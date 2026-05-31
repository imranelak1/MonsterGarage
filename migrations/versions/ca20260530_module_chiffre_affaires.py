"""module chiffre affaires manuel

Revision ID: ca20260530
Revises: a6f2d9c8b4e1
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


revision = "ca20260530"
down_revision = "a6f2d9c8b4e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entrees_chiffre_affaires",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("montant", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "source",
            sa.Enum("atelier", "sntl", "pieces", "autre", name="source_chiffre_affaires"),
            nullable=False,
        ),
        sa.Column("libelle", sa.String(length=150), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["utilisateurs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_entrees_chiffre_affaires_date"), "entrees_chiffre_affaires", ["date"], unique=False)
    op.create_index(op.f("ix_entrees_chiffre_affaires_source"), "entrees_chiffre_affaires", ["source"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_entrees_chiffre_affaires_source"), table_name="entrees_chiffre_affaires")
    op.drop_index(op.f("ix_entrees_chiffre_affaires_date"), table_name="entrees_chiffre_affaires")
    op.drop_table("entrees_chiffre_affaires")

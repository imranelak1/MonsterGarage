"""schema initial

Revision ID: 0001_schema_initial
Revises:
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_schema_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entreprise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raison_sociale", sa.String(length=100), nullable=False),
        sa.Column("nom_commercial", sa.String(length=100), nullable=True),
        sa.Column("adresse", sa.Text(), nullable=False),
        sa.Column("ville", sa.String(length=50), nullable=True),
        sa.Column("telephones", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("rc", sa.String(length=20), nullable=True),
        sa.Column("if_fiscal", sa.String(length=20), nullable=True),
        sa.Column("ice", sa.String(length=20), nullable=True),
        sa.Column("patente", sa.String(length=20), nullable=True),
        sa.Column("cnss", sa.String(length=20), nullable=True),
        sa.Column("rib", sa.String(length=30), nullable=True),
        sa.Column("agrement_sntl", sa.String(length=20), nullable=True),
        sa.Column("logo_path", sa.String(length=255), nullable=True),
        sa.Column("papier_entete_excel_path", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "parametres_systeme",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cle", sa.String(length=50), nullable=False),
        sa.Column("valeur", sa.Text(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("type_valeur", sa.Enum("string", "int", "float", "bool", "json", name="type_valeur_parametre"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cle"),
    )

    op.create_table(
        "utilisateurs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nom_complet", sa.String(length=100), nullable=False),
        sa.Column("login", sa.String(length=50), nullable=False),
        sa.Column("mot_de_passe_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("admin", "secretaire", name="role_utilisateur"), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False),
        sa.Column("derniere_connexion", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login"),
    )
    op.create_index(op.f("ix_utilisateurs_login"), "utilisateurs", ["login"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_utilisateurs_login"), table_name="utilisateurs")
    op.drop_table("utilisateurs")
    op.drop_table("parametres_systeme")
    op.drop_table("entreprise")


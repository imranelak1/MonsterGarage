"""module rh employes avances salaires

Revision ID: c9d4e7f2a8b1
Revises: b4e72df36c91
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d4e7f2a8b1"
down_revision = "b4e72df36c91"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nom_complet", sa.String(length=100), nullable=False),
        sa.Column("cin", sa.String(length=20), nullable=True),
        sa.Column(
            "fonction",
            sa.Enum(
                "gerant",
                "chef_atelier",
                "mecanicien",
                "electricien",
                "tolier",
                "peintre",
                "diagnostic",
                "mecanicien_nautique",
                "ouvrier",
                "administratif",
                "autre",
                name="fonction_employe",
            ),
            nullable=False,
        ),
        sa.Column("telephone", sa.String(length=20), nullable=True),
        sa.Column("adresse", sa.Text(), nullable=True),
        sa.Column("date_embauche", sa.Date(), nullable=True),
        sa.Column(
            "type_remuneration",
            sa.Enum("salaire_fixe", "tache", "mixte", name="type_remuneration_employe"),
            nullable=False,
        ),
        sa.Column("salaire_quinzaine", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("taux_journalier", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("employes") as batch_op:
        batch_op.create_index(batch_op.f("ix_employes_actif"), ["actif"], unique=False)
        batch_op.create_index(batch_op.f("ix_employes_nom_complet"), ["nom_complet"], unique=False)

    op.create_table(
        "avances_salaires",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("montant", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "avance",
                "prime",
                "tache",
                "credit",
                "frais",
                "cumul",
                "reste_du",
                name="type_avance_salaire",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("vehicule_id", sa.Integer(), nullable=True),
        sa.Column(
            "quinzaine",
            sa.Enum("premiere", "seconde", name="quinzaine_avance"),
            nullable=True,
        ),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("montant_total_convenu", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("reste_du", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["employe_id"], ["employes.id"]),
        sa.ForeignKeyConstraint(["vehicule_id"], ["vehicules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("avances_salaires") as batch_op:
        batch_op.create_index(batch_op.f("ix_avances_salaires_employe_id"), ["employe_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_avances_salaires_mois_annee"), ["annee", "mois"], unique=False)
        batch_op.create_index(batch_op.f("ix_avances_salaires_type"), ["type"], unique=False)

    op.create_table(
        "salaires",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employe_id", sa.Integer(), nullable=False),
        sa.Column(
            "type_paie",
            sa.Enum("quinzaine", "fin_mois", "special", name="type_paie_salaire"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("salaire_brut", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_avances", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_primes", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("montant_net_paye", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("jours_ouvrables", sa.Integer(), nullable=True),
        sa.Column("jours_travailles", sa.Integer(), nullable=True),
        sa.Column("taux_journalier", sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["employe_id"], ["employes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("salaires") as batch_op:
        batch_op.create_index(batch_op.f("ix_salaires_employe_id"), ["employe_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_salaires_mois_annee"), ["annee", "mois"], unique=False)
        batch_op.create_index(batch_op.f("ix_salaires_type_paie"), ["type_paie"], unique=False)


def downgrade():
    with op.batch_alter_table("salaires") as batch_op:
        batch_op.drop_index(batch_op.f("ix_salaires_type_paie"))
        batch_op.drop_index(batch_op.f("ix_salaires_mois_annee"))
        batch_op.drop_index(batch_op.f("ix_salaires_employe_id"))
    op.drop_table("salaires")

    with op.batch_alter_table("avances_salaires") as batch_op:
        batch_op.drop_index(batch_op.f("ix_avances_salaires_type"))
        batch_op.drop_index(batch_op.f("ix_avances_salaires_mois_annee"))
        batch_op.drop_index(batch_op.f("ix_avances_salaires_employe_id"))
    op.drop_table("avances_salaires")

    with op.batch_alter_table("employes") as batch_op:
        batch_op.drop_index(batch_op.f("ix_employes_nom_complet"))
        batch_op.drop_index(batch_op.f("ix_employes_actif"))
    op.drop_table("employes")

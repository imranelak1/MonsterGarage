"""pilotage documents pieces reglements

Revision ID: f9a1b2c3d4e5
Revises: a6f2d9c8b4e1
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "f9a1b2c3d4e5"
down_revision = "a6f2d9c8b4e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dossiers_reparation", sa.Column("responsable_id", sa.Integer(), nullable=True))
    op.add_column(
        "dossiers_reparation",
        sa.Column("priorite", sa.String(length=20), nullable=False, server_default="normale"),
    )
    op.add_column("dossiers_reparation", sa.Column("date_promesse", sa.Date(), nullable=True))
    op.add_column("dossiers_reparation", sa.Column("motif_blocage", sa.Text(), nullable=True))
    op.create_index(op.f("ix_dossiers_reparation_responsable_id"), "dossiers_reparation", ["responsable_id"], unique=False)
    op.create_index(op.f("ix_dossiers_reparation_priorite"), "dossiers_reparation", ["priorite"], unique=False)

    op.add_column("journal_actions", sa.Column("objet_type", sa.String(length=50), nullable=True))
    op.add_column("journal_actions", sa.Column("objet_id", sa.Integer(), nullable=True))
    op.add_column("journal_actions", sa.Column("ancien_statut", sa.String(length=50), nullable=True))
    op.add_column("journal_actions", sa.Column("nouveau_statut", sa.String(length=50), nullable=True))
    op.add_column("journal_actions", sa.Column("metadonnees", sa.Text(), nullable=True))
    op.add_column("journal_actions", sa.Column("ip_adresse", sa.String(length=45), nullable=True))

    op.create_table(
        "documents_dossier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("categorie", sa.String(length=40), nullable=False),
        sa.Column("nom_original", sa.String(length=255), nullable=False),
        sa.Column("nom_stockage", sa.String(length=255), nullable=False),
        sa.Column("chemin_relatif", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("taille_octets", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers_reparation.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["utilisateurs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nom_stockage"),
    )
    with op.batch_alter_table("documents_dossier") as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_dossier_dossier_id"), ["dossier_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_documents_dossier_categorie"), ["categorie"], unique=False)

    op.create_table(
        "pieces_dossier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("ligne_devis_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(length=200), nullable=False),
        sa.Column("quantite", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("fournisseur", sa.String(length=120), nullable=True),
        sa.Column("prix_achat_ht", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("statut", sa.String(length=30), nullable=False),
        sa.Column("date_prevue", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["utilisateurs.id"]),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers_reparation.id"]),
        sa.ForeignKeyConstraint(["ligne_devis_id"], ["lignes_devis_reparation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pieces_dossier") as batch_op:
        batch_op.create_index(batch_op.f("ix_pieces_dossier_dossier_id"), ["dossier_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pieces_dossier_ligne_devis_id"), ["ligne_devis_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pieces_dossier_statut"), ["statut"], unique=False)

    op.create_table(
        "reglements_facture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("facture_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("montant", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("mode_reglement", sa.String(length=20), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["utilisateurs.id"]),
        sa.ForeignKeyConstraint(["facture_id"], ["factures_reparation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reglements_facture") as batch_op:
        batch_op.create_index(batch_op.f("ix_reglements_facture_facture_id"), ["facture_id"], unique=False)


def downgrade():
    with op.batch_alter_table("reglements_facture") as batch_op:
        batch_op.drop_index(batch_op.f("ix_reglements_facture_facture_id"))
    op.drop_table("reglements_facture")

    with op.batch_alter_table("pieces_dossier") as batch_op:
        batch_op.drop_index(batch_op.f("ix_pieces_dossier_statut"))
        batch_op.drop_index(batch_op.f("ix_pieces_dossier_ligne_devis_id"))
        batch_op.drop_index(batch_op.f("ix_pieces_dossier_dossier_id"))
    op.drop_table("pieces_dossier")

    with op.batch_alter_table("documents_dossier") as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_dossier_categorie"))
        batch_op.drop_index(batch_op.f("ix_documents_dossier_dossier_id"))
    op.drop_table("documents_dossier")

    op.drop_column("journal_actions", "ip_adresse")
    op.drop_column("journal_actions", "metadonnees")
    op.drop_column("journal_actions", "nouveau_statut")
    op.drop_column("journal_actions", "ancien_statut")
    op.drop_column("journal_actions", "objet_id")
    op.drop_column("journal_actions", "objet_type")

    op.drop_index(op.f("ix_dossiers_reparation_priorite"), table_name="dossiers_reparation")
    op.drop_index(op.f("ix_dossiers_reparation_responsable_id"), table_name="dossiers_reparation")
    op.drop_column("dossiers_reparation", "motif_blocage")
    op.drop_column("dossiers_reparation", "date_promesse")
    op.drop_column("dossiers_reparation", "priorite")
    op.drop_column("dossiers_reparation", "responsable_id")

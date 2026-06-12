"""recalcul tva devis occasion

Revision ID: e20260606
Revises: d20260605
Create Date: 2026-06-06
"""

from alembic import op


revision = "e20260606"
down_revision = "d20260605"
branch_labels = None
depends_on = None


_HT_SUBQUERY = """
(
    SELECT COALESCE(SUM(l.total_ht), 0)
    FROM lignes_devis_reparation AS l
    WHERE l.devis_id = devis_reparation.id
)
"""

_TVA_SUBQUERY = """
(
    SELECT COALESCE(SUM(
        CASE
            WHEN c.type != 'sntl'
             AND COALESCE(l.type_ligne, 'piece') = 'piece'
             AND l.etat_piece = 'occasion'
            THEN 0
            ELSE l.total_ht * 0.20
        END
    ), 0)
    FROM lignes_devis_reparation AS l
    JOIN dossiers_reparation AS d ON d.id = devis_reparation.dossier_id
    JOIN clients AS c ON c.id = d.client_id
    WHERE l.devis_id = devis_reparation.id
)
"""


def upgrade():
    op.execute(
        f"""
        UPDATE devis_reparation
        SET montant_ht = {_HT_SUBQUERY},
            montant_tva = {_TVA_SUBQUERY},
            montant_ttc = ({_HT_SUBQUERY} + {_TVA_SUBQUERY})
        """
    )


def downgrade():
    op.execute(
        f"""
        UPDATE devis_reparation
        SET montant_ht = {_HT_SUBQUERY},
            montant_tva = ({_HT_SUBQUERY} * 0.20),
            montant_ttc = ({_HT_SUBQUERY} * 1.20)
        """
    )

from datetime import datetime, timezone

from app.extensions import db


class AvanceClient(db.Model):
    __tablename__ = "avances_clients"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    montant = db.Column(db.Numeric(12, 2), nullable=False)
    mode_reglement = db.Column(
        db.Enum("especes", "cheque", "virement", "carte", "autre", name="mode_reglement_avance_client"),
        nullable=False,
        default="especes",
    )
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    dossier = db.relationship("DossierReparation", back_populates="avances_client")
    created_by = db.relationship("Utilisateur")

    @property
    def mode_reglement_libelle(self) -> str:
        modes = {
            "especes": "Espèces",
            "cheque": "Chèque",
            "virement": "Virement",
            "carte": "Carte bancaire",
            "autre": "Autre",
        }
        return modes.get(self.mode_reglement, self.mode_reglement or "-")

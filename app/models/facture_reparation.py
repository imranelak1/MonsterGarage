from datetime import datetime, timezone

from app.extensions import db


class FactureReparation(db.Model):
    __tablename__ = "factures_reparation"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), unique=True, nullable=False, index=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, unique=True, index=True)
    devis_id = db.Column(db.Integer, db.ForeignKey("devis_reparation.id"), nullable=False, index=True)
    statut = db.Column(
        db.Enum("emise", "livree", "reglee", "annulee", name="statut_facture_reparation"),
        default="emise",
        nullable=False,
        index=True,
    )
    montant_ht = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    montant_tva = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    montant_ttc = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    montant_regle = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    mode_reglement = db.Column(db.Enum("especes", "cheque", "virement", "carte", "autre", name="mode_reglement_facture"))
    reference_reglement = db.Column(db.String(100))
    livree_le = db.Column(db.DateTime)
    reglee_le = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    dossier = db.relationship("DossierReparation", back_populates="facture")
    devis = db.relationship("DevisReparation")
    created_by = db.relationship("Utilisateur")
    reglements = db.relationship(
        "ReglementFacture",
        back_populates="facture",
        cascade="all, delete-orphan",
        order_by="ReglementFacture.created_at",
    )

    @property
    def statut_libelle(self) -> str:
        if self.statut == "livree" and self.montant_regle and self.montant_regle > 0:
            return "Partiellement reglee"

        statuts = {
            "emise": "Émise",
            "livree": "Livrée",
            "reglee": "Réglée",
            "annulee": "Annulée",
        }
        return statuts.get(self.statut, self.statut)

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

    @property
    def montant_restant(self):
        restant = self.montant_ttc - (self.montant_regle or 0)
        return max(restant, 0)


class ReglementFacture(db.Model):
    __tablename__ = "reglements_facture"

    id = db.Column(db.Integer, primary_key=True)
    facture_id = db.Column(db.Integer, db.ForeignKey("factures_reparation.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    montant = db.Column(db.Numeric(12, 2), nullable=False)
    mode_reglement = db.Column(db.Enum("especes", "cheque", "virement", "carte", "autre", name="mode_reglement_facture"))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    facture = db.relationship("FactureReparation", back_populates="reglements")
    created_by = db.relationship("Utilisateur")

    @property
    def mode_reglement_libelle(self) -> str:
        modes = {
            "especes": "EspÃ¨ces",
            "cheque": "ChÃ¨que",
            "virement": "Virement",
            "carte": "Carte bancaire",
            "autre": "Autre",
        }
        return modes.get(self.mode_reglement, self.mode_reglement or "-")

from datetime import datetime, timezone

from app.extensions import db


class DevisReparation(db.Model):
    __tablename__ = "devis_reparation"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    statut = db.Column(db.Enum("pending", "approved", "rejected", name="statut_devis_reparation"), default="pending", nullable=False)
    objet = db.Column(db.String(200), nullable=False)
    montant_ht = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    montant_tva = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    montant_ttc = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    est_complementaire = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text)
    mode_accord = db.Column(db.Enum("telephone", "signature", "presentiel", "systeme", name="mode_accord_devis"))
    accord_client = db.Column(db.Boolean, default=False, nullable=False)
    accord_assurance = db.Column(db.Boolean, default=False, nullable=False)
    approuve_le = db.Column(db.DateTime)
    approuve_par_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    motif_refus = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    dossier = db.relationship("DossierReparation", back_populates="devis")
    lignes = db.relationship("LigneDevisReparation", back_populates="devis", cascade="all, delete-orphan")
    created_by = db.relationship("Utilisateur", foreign_keys=[created_by_id])
    approuve_par = db.relationship("Utilisateur", foreign_keys=[approuve_par_id])

    __table_args__ = (db.UniqueConstraint("dossier_id", "version", name="uq_devis_reparation_version"),)

    @property
    def statut_libelle(self) -> str:
        statuts = {
            "pending": "En attente",
            "approved": "Approuvé",
            "rejected": "Refusé",
        }
        return statuts.get(self.statut, self.statut)

    @property
    def mode_accord_libelle(self) -> str:
        modes = {
            "telephone": "Telephone",
            "signature": "Signature",
            "presentiel": "Presentiel",
            "systeme": "Systeme",
        }
        return modes.get(self.mode_accord, self.mode_accord or "-")

    @property
    def type_libelle(self) -> str:
        return "Complémentaire" if self.est_complementaire else "Version complète"


class LigneDevisReparation(db.Model):
    __tablename__ = "lignes_devis_reparation"

    id = db.Column(db.Integer, primary_key=True)
    devis_id = db.Column(db.Integer, db.ForeignKey("devis_reparation.id"), nullable=False, index=True)
    designation = db.Column(db.String(200), nullable=False)
    quantite = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    prix_unitaire_ht = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_ht = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    type_ligne = db.Column(
        db.Enum("piece", "main_oeuvre", "autre", name="type_ligne_devis"),
        default="piece",
        nullable=False,
    )
    etat_piece = db.Column(
        db.Enum("neuf", "occasion", "mo", "autre", name="etat_piece_devis"),
        default="neuf",
        nullable=False,
    )
    etat_piece_autre = db.Column(db.String(80))
    type_mo = db.Column(
        db.Enum(
            "mecanique",
            "electricite",
            "tolerie",
            "peinture",
            "diagnostic",
            "autre",
            name="type_main_oeuvre_devis",
        )
    )

    devis = db.relationship("DevisReparation", back_populates="lignes")

    @property
    def etat_piece_libelle(self) -> str:
        labels = {
            "neuf": "Neuf",
            "occasion": "Occasion",
            "mo": "M.O",
            "autre": self.etat_piece_autre or "Autre",
        }
        return labels.get(self.etat_piece, self.etat_piece or "-")

    @property
    def type_ligne_libelle(self) -> str:
        labels = {
            "piece": "Pièce",
            "main_oeuvre": "Main d'œuvre",
            "autre": "Autre",
        }
        return labels.get(self.type_ligne, self.type_ligne or "-")

    @property
    def type_mo_libelle(self) -> str:
        labels = {
            "mecanique": "Mécanique",
            "electricite": "Électricité",
            "tolerie": "Tôlerie",
            "peinture": "Peinture",
            "diagnostic": "Diagnostic",
            "autre": "Autre",
        }
        return labels.get(self.type_mo, self.type_mo or "-")

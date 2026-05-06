from datetime import datetime, timezone

from app.extensions import db


class DossierReparation(db.Model):
    __tablename__ = "dossiers_reparation"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), unique=True, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    vehicule_id = db.Column(db.Integer, db.ForeignKey("vehicules.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    statut = db.Column(
        db.Enum(
            "pending_devis",
            "pending_approval",
            "in_progress",
            "paused_pending_approval",
            "completed",
            "cancelled",
            name="statut_dossier_reparation",
        ),
        default="pending_devis",
        nullable=False,
        index=True,
    )
    demande_client = db.Column(db.Text, nullable=False)
    diagnostic_initial = db.Column(db.Text)
    assurance_nom = db.Column(db.String(100))
    kilometrage_entree = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    client = db.relationship("Client", backref="dossiers_reparation")
    vehicule = db.relationship("Vehicule", backref="dossiers_reparation")
    created_by = db.relationship("Utilisateur", foreign_keys=[created_by_id])
    devis = db.relationship(
        "DevisReparation",
        back_populates="dossier",
        cascade="all, delete-orphan",
        order_by="DevisReparation.version",
    )
    facture = db.relationship(
        "FactureReparation",
        back_populates="dossier",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def statut_libelle(self) -> str:
        statuts = {
            "pending_devis": "En attente de devis",
            "pending_approval": "En attente d'accord",
            "in_progress": "En réparation",
            "paused_pending_approval": "En pause - accord requis",
            "completed": "Terminé",
            "cancelled": "Annulé",
        }
        return statuts.get(self.statut, self.statut)

    @property
    def dernier_devis(self):
        if not self.devis:
            return None
        return max(self.devis, key=lambda devis: devis.version)

    @property
    def dernier_devis_approuve(self):
        devis_approuves = [devis for devis in self.devis if devis.statut == "approved"]
        if not devis_approuves:
            return None
        return max(devis_approuves, key=lambda devis: devis.version)


class JournalAction(db.Model):
    __tablename__ = "journal_actions"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    dossier = db.relationship("DossierReparation", backref="journal")
    utilisateur = db.relationship("Utilisateur")

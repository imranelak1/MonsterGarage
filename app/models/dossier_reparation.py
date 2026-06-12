from datetime import datetime, timezone
from decimal import Decimal

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
            "cancelled_billable",
            name="statut_dossier_reparation",
        ),
        default="pending_devis",
        nullable=False,
        index=True,
    )
    demande_client = db.Column(db.Text, nullable=False)
    diagnostic_initial = db.Column(db.Text)
    assurance_nom = db.Column(db.String(100))
    numero_bon_sntl = db.Column(db.String(50))
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
    avances_client = db.relationship(
        "AvanceClient",
        back_populates="dossier",
        cascade="all, delete-orphan",
        order_by="AvanceClient.date",
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
            "cancelled_billable": "Annule - travaux a facturer",
        }
        return statuts.get(self.statut, self.statut)

    @property
    def est_facturable(self) -> bool:
        return self.statut in {"completed", "cancelled_billable"}

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

    @property
    def devis_approuves_facturables(self):
        devis_approuves = sorted(
            [devis for devis in self.devis if devis.statut == "approved"],
            key=lambda devis: devis.version,
        )
        if not devis_approuves:
            return []

        devis_base = [devis for devis in devis_approuves if not devis.est_complementaire]
        if not devis_base:
            return devis_approuves

        dernier_devis_base = devis_base[-1]
        return [
            devis
            for devis in devis_approuves
            if devis == dernier_devis_base
            or (devis.est_complementaire and devis.version > dernier_devis_base.version)
        ]

    @property
    def devis_complementaires_facturables(self):
        devis_approuves = sorted(
            [devis for devis in self.devis if devis.statut == "approved"],
            key=lambda devis: devis.version,
        )
        devis_base = [devis for devis in devis_approuves if not devis.est_complementaire]
        if not devis_base:
            return [devis for devis in devis_approuves if devis.est_complementaire]

        dernier_devis_base = devis_base[-1]
        return [
            devis
            for devis in devis_approuves
            if devis.est_complementaire and devis.version > dernier_devis_base.version
        ]

    @property
    def montant_avances_client(self):
        return sum(
            (Decimal(str(avance.montant or 0)) for avance in self.avances_client),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))


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

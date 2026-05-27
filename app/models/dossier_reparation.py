from datetime import date, datetime, timezone

from app.extensions import db


class DossierReparation(db.Model):
    __tablename__ = "dossiers_reparation"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), unique=True, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    vehicule_id = db.Column(db.Integer, db.ForeignKey("vehicules.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    responsable_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), index=True)
    priorite = db.Column(db.String(20), default="normale", nullable=False, index=True)
    date_promesse = db.Column(db.Date)
    motif_blocage = db.Column(db.Text)
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
    responsable = db.relationship("Utilisateur", foreign_keys=[responsable_id])
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
            "cancelled_billable": "Annule - travaux a facturer",
        }
        return statuts.get(self.statut, self.statut)

    @property
    def priorite_libelle(self) -> str:
        priorites = {
            "basse": "Basse",
            "normale": "Normale",
            "haute": "Haute",
            "urgente": "Urgente",
        }
        return priorites.get(self.priorite, self.priorite or "Normale")

    @property
    def date_promesse_depassee(self) -> bool:
        statuts_ouverts = {"pending_devis", "pending_approval", "in_progress", "paused_pending_approval"}
        return bool(self.date_promesse and self.date_promesse < date.today() and self.statut in statuts_ouverts)

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


class JournalAction(db.Model):
    __tablename__ = "journal_actions"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text)
    objet_type = db.Column(db.String(50))
    objet_id = db.Column(db.Integer)
    ancien_statut = db.Column(db.String(50))
    nouveau_statut = db.Column(db.String(50))
    metadonnees = db.Column(db.Text)
    ip_adresse = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    dossier = db.relationship("DossierReparation", backref="journal")
    utilisateur = db.relationship("Utilisateur")


class DocumentDossier(db.Model):
    __tablename__ = "documents_dossier"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    categorie = db.Column(db.String(40), default="autre", nullable=False, index=True)
    nom_original = db.Column(db.String(255), nullable=False)
    nom_stockage = db.Column(db.String(255), nullable=False, unique=True)
    chemin_relatif = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    taille_octets = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    dossier = db.relationship("DossierReparation", backref="documents")
    uploaded_by = db.relationship("Utilisateur")

    @property
    def categorie_libelle(self) -> str:
        categories = {
            "photo_entree": "Photo entree",
            "carte_grise": "Carte grise",
            "or_sntl": "Bon / OR SNTL",
            "devis_signe": "Devis signe",
            "accord_assurance": "Accord assurance",
            "photo_travaux": "Photo travaux",
            "bon_livraison": "Bon de livraison",
            "autre": "Autre",
        }
        return categories.get(self.categorie, self.categorie)


class PieceDossier(db.Model):
    __tablename__ = "pieces_dossier"

    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey("dossiers_reparation.id"), nullable=False, index=True)
    ligne_devis_id = db.Column(db.Integer, db.ForeignKey("lignes_devis_reparation.id"), index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    designation = db.Column(db.String(200), nullable=False)
    quantite = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    fournisseur = db.Column(db.String(120))
    prix_achat_ht = db.Column(db.Numeric(10, 2))
    statut = db.Column(db.String(30), default="a_commander", nullable=False, index=True)
    date_prevue = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    dossier = db.relationship("DossierReparation", backref="pieces")
    ligne_devis = db.relationship("LigneDevisReparation")
    created_by = db.relationship("Utilisateur")

    @property
    def statut_libelle(self) -> str:
        statuts = {
            "a_commander": "A commander",
            "commandee": "Commandee",
            "recue": "Recue",
            "annulee": "Annulee",
        }
        return statuts.get(self.statut, self.statut)

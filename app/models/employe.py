from datetime import datetime, timezone

from app.extensions import db


class Employe(db.Model):
    __tablename__ = "employes"

    id = db.Column(db.Integer, primary_key=True)
    nom_complet = db.Column(db.String(100), nullable=False)
    cin = db.Column(db.String(20))
    fonction = db.Column(
        db.Enum(
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
    )
    telephone = db.Column(db.String(20))
    adresse = db.Column(db.Text)
    date_embauche = db.Column(db.Date)

    type_remuneration = db.Column(
        db.Enum("salaire_fixe", "tache", "mixte", name="type_remuneration_employe"),
        nullable=False,
        default="tache",
    )
    salaire_quinzaine = db.Column(db.Numeric(10, 2))
    taux_journalier = db.Column(db.Numeric(10, 2))

    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    avances = db.relationship(
        "AvanceSalaire", back_populates="employe", cascade="all, delete-orphan"
    )
    salaires = db.relationship(
        "Salaire", back_populates="employe", cascade="all, delete-orphan"
    )

    _FONCTIONS = {
        "gerant": "Gérant",
        "chef_atelier": "Chef Atelier",
        "mecanicien": "Mécanicien",
        "electricien": "Électricien",
        "tolier": "Tôlier",
        "peintre": "Peintre",
        "diagnostic": "Diagnostic",
        "mecanicien_nautique": "Mécanicien Nautique",
        "ouvrier": "Ouvrier",
        "administratif": "Administratif",
        "autre": "Autre",
    }

    @property
    def fonction_libelle(self):
        return self._FONCTIONS.get(self.fonction, self.fonction)

    @property
    def type_remuneration_libelle(self):
        labels = {"salaire_fixe": "Salaire fixe", "tache": "À la tâche", "mixte": "Mixte"}
        return labels.get(self.type_remuneration, self.type_remuneration)

    def __repr__(self):
        return f"<Employe {self.nom_complet}>"

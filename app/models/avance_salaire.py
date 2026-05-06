from datetime import datetime, timezone

from app.extensions import db


class AvanceSalaire(db.Model):
    __tablename__ = "avances_salaires"

    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(
        db.Integer, db.ForeignKey("employes.id"), nullable=False
    )

    date = db.Column(db.Date, nullable=False)
    montant = db.Column(db.Numeric(10, 2), nullable=False)

    type = db.Column(
        db.Enum(
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
    )

    description = db.Column(db.String(200))
    vehicule_id = db.Column(
        db.Integer, db.ForeignKey("vehicules.id"), nullable=True
    )

    quinzaine = db.Column(
        db.Enum("premiere", "seconde", name="quinzaine_avance"), nullable=True
    )
    mois = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)

    # Pour les tâches avec reste dû (ex: AYOUB)
    montant_total_convenu = db.Column(db.Numeric(10, 2))
    reste_du = db.Column(db.Numeric(10, 2))

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    employe = db.relationship("Employe", back_populates="avances")
    vehicule = db.relationship("Vehicule")

    _TYPES = {
        "avance": "Avance",
        "prime": "Prime",
        "tache": "Tâche",
        "credit": "Crédit",
        "frais": "Frais",
        "cumul": "Cumul",
        "reste_du": "Reste dû",
    }

    @property
    def type_libelle(self):
        return self._TYPES.get(self.type, self.type)

    @property
    def est_salaire(self):
        """Retourne False pour les types qui ne comptent pas comme salaire."""
        return self.type not in ("frais",)

    def __repr__(self):
        return f"<AvanceSalaire {self.employe_id} {self.date} {self.montant} {self.type}>"

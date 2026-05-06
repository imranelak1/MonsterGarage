from datetime import datetime, timezone

from app.extensions import db


class Salaire(db.Model):
    __tablename__ = "salaires"

    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(
        db.Integer, db.ForeignKey("employes.id"), nullable=False
    )

    type_paie = db.Column(
        db.Enum("quinzaine", "fin_mois", "special", name="type_paie_salaire"),
        nullable=False,
    )
    date = db.Column(db.Date, nullable=False)
    mois = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)

    salaire_brut = db.Column(db.Numeric(10, 2), nullable=False)
    total_avances = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    total_primes = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    montant_net_paye = db.Column(db.Numeric(10, 2), nullable=False)

    # Prorata (renseigné uniquement si applicable)
    jours_ouvrables = db.Column(db.Integer)
    jours_travailles = db.Column(db.Integer)
    taux_journalier = db.Column(db.Numeric(10, 5))

    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    employe = db.relationship("Employe", back_populates="salaires")

    _TYPES_PAIE = {
        "quinzaine": "Quinzaine",
        "fin_mois": "Solde fin de mois",
        "special": "Paiement spécial",
    }

    @property
    def type_paie_libelle(self):
        return self._TYPES_PAIE.get(self.type_paie, self.type_paie)

    @property
    def est_prorata(self):
        return (
            self.jours_travailles is not None
            and self.jours_ouvrables is not None
            and self.jours_travailles < self.jours_ouvrables
        )

    def __repr__(self):
        return f"<Salaire {self.employe_id} {self.type_paie} {self.mois}/{self.annee}>"

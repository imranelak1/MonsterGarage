from datetime import datetime, timezone

from app.extensions import db


class Vehicule(db.Model):
    __tablename__ = "vehicules"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    immatriculation = db.Column(db.String(30), nullable=False, index=True)
    type_immatriculation = db.Column(
        db.Enum("standard", "administrative", "ww", "etranger", name="type_immatriculation"),
        default="standard",
    )
    vin = db.Column(db.String(17), index=True)
    marque = db.Column(db.String(50), nullable=False)
    modele = db.Column(db.String(50), nullable=False)
    annee = db.Column(db.Integer)
    couleur = db.Column(db.String(30))
    type_carburant = db.Column(
        db.Enum("essence", "diesel", "electrique", "hybride", name="type_carburant"),
    )
    type_vehicule = db.Column(
        db.Enum("voiture", "utilitaire", "camion", "moto", "engin", "bateau", name="type_vehicule"),
        default="voiture",
    )
    kilometrage_actuel = db.Column(db.Integer)
    derniere_visite = db.Column(db.Date)
    notes = db.Column(db.Text)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    client = db.relationship("Client", back_populates="vehicules")

    @property
    def libelle(self) -> str:
        return f"{self.marque} {self.modele} - {self.immatriculation}"


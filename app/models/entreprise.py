from datetime import datetime, timezone

from app.extensions import db


class Entreprise(db.Model):
    __tablename__ = "entreprise"

    id = db.Column(db.Integer, primary_key=True)
    raison_sociale = db.Column(db.String(100), nullable=False)
    nom_commercial = db.Column(db.String(100))
    adresse = db.Column(db.Text, nullable=False)
    ville = db.Column(db.String(50), default="Marrakech")
    telephones = db.Column(db.String(100))
    email = db.Column(db.String(100))
    rc = db.Column(db.String(20))
    if_fiscal = db.Column(db.String(20))
    ice = db.Column(db.String(20))
    patente = db.Column(db.String(20))
    cnss = db.Column(db.String(20))
    rib = db.Column(db.String(30))
    agrement_sntl = db.Column(db.String(20))
    logo_path = db.Column(db.String(255))
    papier_entete_excel_path = db.Column(db.String(255))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


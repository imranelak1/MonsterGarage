from datetime import datetime, timezone

from app.extensions import db


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    type = db.Column(
        db.Enum("particulier", "administration", "sntl", name="type_client"),
        nullable=False,
    )
    nom = db.Column(db.String(150), nullable=False, index=True)
    sigle = db.Column(db.String(50))
    telephone = db.Column(db.String(20))
    telephone_2 = db.Column(db.String(20))
    email = db.Column(db.String(100))
    adresse = db.Column(db.Text)
    ville = db.Column(db.String(50))
    ice = db.Column(db.String(20))
    if_fiscal = db.Column(db.String(20))
    rc = db.Column(db.String(20))
    administration_rattachee = db.Column(db.String(100))
    delai_paiement_jours = db.Column(db.Integer, default=30, nullable=False)
    plafond_credit = db.Column(db.Numeric(12, 2))
    notes = db.Column(db.Text)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    vehicules = db.relationship("Vehicule", back_populates="client", cascade="all, delete-orphan")

    @property
    def type_libelle(self) -> str:
        types = {
            "particulier": "Particulier",
            "administration": "Administration",
            "sntl": "Administration SNTL",
        }
        return types.get(self.type, self.type)

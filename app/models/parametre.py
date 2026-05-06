from datetime import datetime, timezone

from app.extensions import db


class ParametreSysteme(db.Model):
    __tablename__ = "parametres_systeme"

    id = db.Column(db.Integer, primary_key=True)
    cle = db.Column(db.String(50), unique=True, nullable=False)
    valeur = db.Column(db.Text)
    description = db.Column(db.String(255))
    type_valeur = db.Column(
        db.Enum("string", "int", "float", "bool", "json", name="type_valeur_parametre"),
        default="string",
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


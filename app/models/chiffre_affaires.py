from datetime import datetime, timezone

from app.extensions import db


class EntreeChiffreAffaires(db.Model):
    __tablename__ = "entrees_chiffre_affaires"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    montant = db.Column(db.Numeric(12, 2), nullable=False)
    source = db.Column(
        db.Enum("atelier", "sntl", "pieces", "autre", name="source_chiffre_affaires"),
        default="atelier",
        nullable=False,
        index=True,
    )
    libelle = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    created_by = db.relationship("Utilisateur")

    @property
    def source_libelle(self) -> str:
        sources = {
            "atelier": "Atelier",
            "sntl": "SNTL",
            "pieces": "Pieces",
            "autre": "Autre",
        }
        return sources.get(self.source, self.source)

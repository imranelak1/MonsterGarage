from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class Utilisateur(UserMixin, db.Model):
    __tablename__ = "utilisateurs"

    id = db.Column(db.Integer, primary_key=True)
    nom_complet = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(50), unique=True, nullable=False, index=True)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "secretaire", name="role_utilisateur"), default="secretaire", nullable=False)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    derniere_connexion = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def definir_mot_de_passe(self, mot_de_passe: str) -> None:
        self.mot_de_passe_hash = generate_password_hash(mot_de_passe)

    def verifier_mot_de_passe(self, mot_de_passe: str) -> bool:
        return check_password_hash(self.mot_de_passe_hash, mot_de_passe)

    @property
    def is_active(self) -> bool:
        return self.actif

    @property
    def est_admin(self) -> bool:
        return self.role == "admin"

    @property
    def role_libelle(self) -> str:
        roles = {
            "admin": "Gérant",
            "secretaire": "Secrétaire",
        }
        return roles.get(self.role, self.role)

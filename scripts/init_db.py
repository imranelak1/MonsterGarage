import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Utilisateur
from app.services.parametres import assurer_parametres_defaut, obtenir_entreprise


def main() -> None:
    app = create_app(os.environ.get("FLASK_CONFIG", "development"))
    with app.app_context():
        db.create_all()

        obtenir_entreprise()
        assurer_parametres_defaut()

        if not Utilisateur.query.first():
            admin = Utilisateur(login="admin", nom_complet="Gérant Monster Garage", role="admin")
            admin.definir_mot_de_passe("admin123")
            db.session.add(admin)

        db.session.commit()
        print("Base de données initialisée.")
        print("Compte par défaut si besoin : admin / admin123")


if __name__ == "__main__":
    main()

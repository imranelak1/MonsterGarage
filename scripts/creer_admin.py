import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Utilisateur


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        login = input("Identifiant admin [admin] : ").strip() or "admin"
        nom = input("Nom complet [Gérant Monster Garage] : ").strip() or "Gérant Monster Garage"
        mot_de_passe = getpass.getpass("Mot de passe : ")

        if not mot_de_passe:
            raise SystemExit("Mot de passe obligatoire.")

        utilisateur = Utilisateur.query.filter_by(login=login).first()
        if not utilisateur:
            utilisateur = Utilisateur(login=login, nom_complet=nom, role="admin")
            db.session.add(utilisateur)

        utilisateur.nom_complet = nom
        utilisateur.role = "admin"
        utilisateur.actif = True
        utilisateur.definir_mot_de_passe(mot_de_passe)
        db.session.commit()
        print(f"Compte admin prêt : {login}")


if __name__ == "__main__":
    main()

from app.extensions import db
from app.models import Entreprise, ParametreSysteme


PARAMETRES_DEFAUT = [
    ("taux_tva", "20", "Taux de TVA par défaut", "float"),
    ("taux_commission_sntl", "10", "Commission SNTL par défaut", "float"),
    ("delai_paiement_default", "30", "Délai de paiement par défaut en jours", "int"),
    ("charges_fixes_mensuelles", "70000", "Charges fixes mensuelles estimées", "float"),
]


def obtenir_entreprise() -> Entreprise:
    entreprise = Entreprise.query.first()
    if entreprise:
        return entreprise

    entreprise = Entreprise(
        raison_sociale="WIDINE MOTORS SERVICES",
        nom_commercial="MONSTER GARAGE",
        adresse="N°534 Bis 2, Quartier Industriel Sidi Ghanem",
        ville="Marrakech",
        telephones="0661 10 90 31 / 0660 63 78 64",
        email="MonstergarageWMS@gmail.com",
        rc="150241",
        if_fiscal="65976431",
        ice="003524622000063",
        patente="64006750",
        rib="007450000612500000095129",
        agrement_sntl="3108",
        logo_path="img/logo_monster_garage.png",
    )
    db.session.add(entreprise)
    db.session.commit()
    return entreprise


def assurer_parametres_defaut() -> None:
    for cle, valeur, description, type_valeur in PARAMETRES_DEFAUT:
        if not ParametreSysteme.query.filter_by(cle=cle).first():
            db.session.add(
                ParametreSysteme(
                    cle=cle,
                    valeur=valeur,
                    description=description,
                    type_valeur=type_valeur,
                )
            )
    db.session.commit()


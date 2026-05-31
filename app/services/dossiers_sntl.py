from app.models import Client, DossierReparation
from app.services.dossiers import (
    RegleMetierErreur,
    generer_numero_bon_sntl,
    normaliser_numero_bon_sntl,
)


SNTL_CLIENTS_PREDEFINIS = {
    "600-85": {"code": "600", "nom": "Commune Harbil", "or_numero": "85"},
    "100-83": {"code": "100", "nom": "Wilaya", "or_numero": "83"},
    "300-84": {"code": "300", "nom": "NARSA", "or_numero": "84"},
    "800-89": {"code": "800", "nom": "AMEE", "or_numero": "89"},
}


def est_dossier_sntl(dossier: DossierReparation) -> bool:
    return bool(dossier and dossier.client and dossier.client.type == "sntl")


def requete_dossiers_sntl():
    return DossierReparation.query.join(DossierReparation.client).filter(Client.type == "sntl")


def assurer_numero_bon_sntl(valeur: str | None = None) -> str:
    return normaliser_numero_bon_sntl(valeur)


def prochain_numero_bon_sntl() -> str:
    return generer_numero_bon_sntl()


def preset_sntl(preset_key: str):
    preset = SNTL_CLIENTS_PREDEFINIS.get((preset_key or "").strip())
    if not preset:
        raise RegleMetierErreur("Code SNTL predefini invalide.")
    return preset


def forcer_piece_neuve() -> str:
    return "neuf"

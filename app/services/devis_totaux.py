from decimal import Decimal


TAUX_TVA_DEFAUT = Decimal("0.20")


def taux_tva_ligne(ligne, type_client: str | None = None) -> Decimal:
    type_ligne = _valeur(ligne, "type_ligne") or "piece"
    etat_piece = _valeur(ligne, "etat_piece") or "neuf"

    if type_client != "sntl" and type_ligne == "piece" and etat_piece == "occasion":
        return Decimal("0.00")
    return TAUX_TVA_DEFAUT


def montant_tva_ligne(ligne, type_client: str | None = None) -> Decimal:
    total_ht = Decimal(str(_valeur(ligne, "total_ht") or 0)).quantize(Decimal("0.01"))
    return (total_ht * taux_tva_ligne(ligne, type_client)).quantize(Decimal("0.01"))


def montant_ttc_ligne(ligne, type_client: str | None = None) -> Decimal:
    total_ht = Decimal(str(_valeur(ligne, "total_ht") or 0)).quantize(Decimal("0.01"))
    return (total_ht + montant_tva_ligne(ligne, type_client)).quantize(Decimal("0.01"))


def calculer_totaux_lignes(lignes, type_client: str | None = None) -> tuple[Decimal, Decimal, Decimal]:
    montant_ht = Decimal("0.00")
    montant_tva = Decimal("0.00")
    for ligne in lignes:
        montant_ht += Decimal(str(_valeur(ligne, "total_ht") or 0))
        montant_tva += montant_tva_ligne(ligne, type_client)

    montant_ht = montant_ht.quantize(Decimal("0.01"))
    montant_tva = montant_tva.quantize(Decimal("0.01"))
    return montant_ht, montant_tva, (montant_ht + montant_tva).quantize(Decimal("0.01"))


def _valeur(ligne, cle: str):
    if isinstance(ligne, dict):
        return ligne.get(cle)
    return getattr(ligne, cle, None)

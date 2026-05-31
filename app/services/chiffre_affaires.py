from decimal import Decimal, InvalidOperation


SOURCES_CA = {
    "atelier": "Atelier",
    "sntl": "SNTL",
    "pieces": "Pieces",
    "autre": "Autre",
}


def decimal_montant_ca(valeur: str | None) -> Decimal:
    try:
        montant = Decimal(str(valeur or "").strip().replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Saisissez un montant de CA valide.") from None

    if montant <= 0:
        raise ValueError("Le montant de CA doit etre superieur a 0.")
    return montant

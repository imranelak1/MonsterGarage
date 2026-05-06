import phonenumbers


def normaliser_telephone(valeur: str | None) -> str:
    numero = (valeur or "").strip()
    if not numero:
        return ""

    try:
        parsed = phonenumbers.parse(numero, "MA")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Numéro de téléphone invalide.") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Numéro de téléphone invalide.")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

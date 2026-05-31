from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from flask import request


@dataclass(frozen=True)
class PeriodeFiltre:
    debut: date | None
    fin: date | None
    valeur_debut: str
    valeur_fin: str


def periode_depuis_requete() -> PeriodeFiltre:
    valeur_debut = request.args.get("date_debut", "").strip()
    valeur_fin = request.args.get("date_fin", "").strip()
    return PeriodeFiltre(
        debut=_date_ou_none(valeur_debut),
        fin=_date_ou_none(valeur_fin),
        valeur_debut=valeur_debut,
        valeur_fin=valeur_fin,
    )


def appliquer_filtre_periode(requete, colonne, periode: PeriodeFiltre):
    if periode.debut:
        requete = requete.filter(colonne >= datetime.combine(periode.debut, time.min))
    if periode.fin:
        lendemain = periode.fin + timedelta(days=1)
        requete = requete.filter(colonne < datetime.combine(lendemain, time.min))
    return requete


def _date_ou_none(valeur: str) -> date | None:
    if not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None

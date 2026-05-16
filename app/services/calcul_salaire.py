import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.avance_salaire import AvanceSalaire
from app.models.employe import Employe
from app.models.salaire import Salaire


class ErreurRH(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers calendrier (samedi ouvrable au Maroc, dimanche chômé)
# ---------------------------------------------------------------------------

def get_jours_ouvrables_quinzaine(mois: int, annee: int, quinzaine: int) -> int:
    """Nombre de jours ouvrables dans une quinzaine (lun–sam, sans dimanche)."""
    if quinzaine == 1:
        debut, fin = date(annee, mois, 1), date(annee, mois, 15)
    else:
        dernier_jour = calendar.monthrange(annee, mois)[1]
        debut, fin = date(annee, mois, 16), date(annee, mois, dernier_jour)

    count = 0
    d = debut
    while d <= fin:
        if d.weekday() != 6:  # 6 = dimanche
            count += 1
        from datetime import timedelta
        d += timedelta(days=1)
    return count


def get_dernier_jour(mois: int, annee: int) -> int:
    return calendar.monthrange(annee, mois)[1]


def get_salaire_quinzaine(employe: Employe) -> Decimal:
    """Montant de référence payé par quinzaine."""
    return Decimal(str(employe.salaire_quinzaine or 0))


# ---------------------------------------------------------------------------
# Lecture des avances depuis la base
# ---------------------------------------------------------------------------

def get_avances_deductibles(employe_id: int, mois: int, annee: int,
                             quinzaine: str) -> Decimal:
    """
    Somme des avances et crédits d'une quinzaine donnée.
    Seuls les types 'avance' et 'credit' sont déduits du salaire.
    Les primes, frais, cumuls, tâches ne sont pas déduits.
    """
    total = (
        AvanceSalaire.query
        .filter(
            AvanceSalaire.employe_id == employe_id,
            AvanceSalaire.mois == mois,
            AvanceSalaire.annee == annee,
            AvanceSalaire.quinzaine == quinzaine,
            AvanceSalaire.type.in_(["avance", "credit"]),
        )
        .with_entities(func.sum(AvanceSalaire.montant))
        .scalar()
    )
    return Decimal(str(total or 0))


def get_total_avances_mois(employe_id: int, mois: int, annee: int,
                            inclure_frais: bool = False) -> Decimal:
    """Somme de toutes les avances (hors quinzaines/soldes) du mois."""
    types_exclus = ["avance", "prime", "tache", "credit", "cumul", "reste_du"]
    if inclure_frais:
        types_exclus.append("frais")

    total = (
        AvanceSalaire.query
        .filter(
            AvanceSalaire.employe_id == employe_id,
            AvanceSalaire.mois == mois,
            AvanceSalaire.annee == annee,
            AvanceSalaire.type.in_(types_exclus),
        )
        .with_entities(func.sum(AvanceSalaire.montant))
        .scalar()
    )
    return Decimal(str(total or 0))


def a_salaire_fin_mois(employe_id: int, mois: int, annee: int) -> bool:
    """Vérifie si un solde fin de mois a été enregistré pour cet employé."""
    return (
        Salaire.query
        .filter(
            Salaire.employe_id == employe_id,
            Salaire.mois == mois,
            Salaire.annee == annee,
            Salaire.type_paie == "fin_mois",
        )
        .first()
    ) is not None


# ---------------------------------------------------------------------------
# Calculs (retournent un dict, n'écrivent pas en base)
# ---------------------------------------------------------------------------

def calculer_quinzaine(employe: Employe, mois: int, annee: int) -> dict | None:
    """
    Calcule la quinzaine du 15 pour un employé à salaire fixe.
    Aucune déduction d'avances à cette étape (règle métier réelle).
    Retourne None pour les employés à la tâche.
    """
    if employe.type_remuneration == "tache":
        return None

    brut = get_salaire_quinzaine(employe)

    return {
        "employe_id": employe.id,
        "type_paie": "quinzaine",
        "date": date(annee, mois, 15),
        "mois": mois,
        "annee": annee,
        "salaire_brut": brut,
        "total_avances": Decimal("0"),
        "total_primes": Decimal("0"),
        "montant_net_paye": brut,
        "jours_ouvrables": None,
        "jours_travailles": None,
        "taux_journalier": None,
    }


def calculer_solde_fin_mois(employe: Employe, mois: int, annee: int,
                             jours_travailles: int | None = None,
                             brut_solde: Decimal | None = None) -> dict | None:
    """
    Calcule le solde de fin de mois.

    Formule standard : brut_2eme_quinzaine − avances_2eme_quinzaine
    Formule prorata  : (brut_2eme_quinzaine / jours_ouvrables × jours_travailles) − avances

    Le taux journalier est tronqué à 5 décimales avant multiplication
    (reproduit le comportement Excel du fichier source, ex: 2250/13 = 173.07692).
    """
    if employe.type_remuneration == "tache":
        return None

    jours_ouvrables = get_jours_ouvrables_quinzaine(mois, annee, quinzaine=2)
    dernier_jour = get_dernier_jour(mois, annee)

    salaire_q = Decimal(str(brut_solde)) if brut_solde is not None else get_salaire_quinzaine(employe)

    if jours_travailles is not None and jours_travailles < jours_ouvrables:
        # Prorata : tronqué à 5 décimales comme dans le fichier Excel source
        taux = (salaire_q / jours_ouvrables).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        )
        brut = (taux * jours_travailles).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
    else:
        taux = (salaire_q / jours_ouvrables).quantize(
            Decimal("0.00001"), rounding=ROUND_DOWN
        )
        brut = salaire_q
        jours_travailles = jours_ouvrables

    avances = get_avances_deductibles(employe.id, mois, annee, quinzaine="seconde")
    net = brut - avances

    return {
        "employe_id": employe.id,
        "type_paie": "fin_mois",
        "date": date(annee, mois, dernier_jour),
        "mois": mois,
        "annee": annee,
        "salaire_brut": brut,
        "total_avances": avances,
        "total_primes": Decimal("0"),
        "montant_net_paye": net,
        "jours_ouvrables": jours_ouvrables,
        "jours_travailles": jours_travailles,
        "taux_journalier": taux,
    }


# ---------------------------------------------------------------------------
# Persistance en base
# ---------------------------------------------------------------------------

def enregistrer_quinzaine(employe: Employe, mois: int, annee: int) -> Salaire:
    """Enregistre la quinzaine en base. Lève ErreurRH si déjà payée."""
    existe = (
        Salaire.query
        .filter_by(employe_id=employe.id, mois=mois, annee=annee, type_paie="quinzaine")
        .first()
    )
    if existe:
        raise ErreurRH(
            f"La quinzaine de {employe.nom_complet} pour {mois}/{annee} est déjà enregistrée."
        )

    data = calculer_quinzaine(employe, mois, annee)
    if data is None:
        raise ErreurRH(
            f"{employe.nom_complet} est à la tâche — pas de quinzaine fixe."
        )

    salaire = Salaire(**data)
    db.session.add(salaire)
    return salaire


def enregistrer_solde_fin_mois(employe: Employe, mois: int, annee: int,
                                jours_travailles: int | None = None,
                                brut_solde: Decimal | None = None,
                                notes: str = "") -> Salaire:
    """Enregistre le solde fin de mois en base. Lève ErreurRH si déjà payé."""
    existe = (
        Salaire.query
        .filter_by(employe_id=employe.id, mois=mois, annee=annee, type_paie="fin_mois")
        .first()
    )
    if existe:
        raise ErreurRH(
            f"Le solde fin de mois de {employe.nom_complet} pour {mois}/{annee} est déjà enregistré."
        )

    data = calculer_solde_fin_mois(employe, mois, annee, jours_travailles, brut_solde)
    if data is None:
        raise ErreurRH(
            f"{employe.nom_complet} est à la tâche — solde à saisir manuellement."
        )

    if notes:
        data["notes"] = notes

    salaire = Salaire(**data)
    db.session.add(salaire)
    return salaire


# ---------------------------------------------------------------------------
# Vue mensuelle et alertes
# ---------------------------------------------------------------------------

def get_recap_mensuel(mois: int, annee: int) -> list[dict]:
    """
    Retourne une ligne de récap par employé actif pour le mois donné.
    Inclut les totaux avances/primes/tâches, quinzaine, solde, et alertes.
    """
    employes = Employe.query.filter_by(actif=True).order_by(Employe.nom_complet).all()
    lignes = []

    for emp in employes:
        # Avances brutes du mois (tous types)
        total_avances = (
            AvanceSalaire.query
            .filter(
                AvanceSalaire.employe_id == emp.id,
                AvanceSalaire.mois == mois,
                AvanceSalaire.annee == annee,
                AvanceSalaire.type.in_(["avance", "credit"]),
            )
            .with_entities(func.sum(AvanceSalaire.montant))
            .scalar() or 0
        )
        total_primes = (
            AvanceSalaire.query
            .filter(
                AvanceSalaire.employe_id == emp.id,
                AvanceSalaire.mois == mois,
                AvanceSalaire.annee == annee,
                AvanceSalaire.type.in_(["prime", "tache", "cumul", "reste_du"]),
            )
            .with_entities(func.sum(AvanceSalaire.montant))
            .scalar() or 0
        )
        total_frais = (
            AvanceSalaire.query
            .filter(
                AvanceSalaire.employe_id == emp.id,
                AvanceSalaire.mois == mois,
                AvanceSalaire.annee == annee,
                AvanceSalaire.type == "frais",
            )
            .with_entities(func.sum(AvanceSalaire.montant))
            .scalar() or 0
        )
        avances_a_deduire = (
            AvanceSalaire.query
            .filter(
                AvanceSalaire.employe_id == emp.id,
                AvanceSalaire.mois == mois,
                AvanceSalaire.annee == annee,
                AvanceSalaire.quinzaine == "seconde",
                AvanceSalaire.type.in_(["avance", "credit"]),
            )
            .with_entities(func.sum(AvanceSalaire.montant))
            .scalar() or 0
        )

        # Quinzaine et solde enregistrés
        quinzaine_rec = (
            Salaire.query
            .filter_by(employe_id=emp.id, mois=mois, annee=annee, type_paie="quinzaine")
            .first()
        )
        solde_rec = (
            Salaire.query
            .filter_by(employe_id=emp.id, mois=mois, annee=annee, type_paie="fin_mois")
            .first()
        )

        # Reste dû en cours
        reste_du_total = (
            AvanceSalaire.query
            .filter(
                AvanceSalaire.employe_id == emp.id,
                AvanceSalaire.mois == mois,
                AvanceSalaire.annee == annee,
                AvanceSalaire.type.in_(["tache", "reste_du"]),
                AvanceSalaire.reste_du.isnot(None),
                AvanceSalaire.reste_du > 0,
            )
            .with_entities(func.sum(AvanceSalaire.reste_du))
            .scalar() or 0
        )

        # Total net salaire affiché : les avances sont déduites au solde, pas ajoutées.
        total_mois = (
            Decimal(str(total_primes))
            + Decimal(str(quinzaine_rec.montant_net_paye if quinzaine_rec else 0))
            + Decimal(str(solde_rec.montant_net_paye if solde_rec else 0))
        )

        # Alertes
        alertes = []
        if emp.type_remuneration in ("salaire_fixe", "mixte"):
            if not quinzaine_rec:
                alertes.append("quinzaine_non_payee")
            if not solde_rec:
                alertes.append("solde_fin_mois_non_paye")
        if reste_du_total:
            alertes.append("reste_du")

        lignes.append({
            "employe": emp,
            "total_avances": Decimal(str(total_avances)),
            "avances_a_deduire": Decimal(str(avances_a_deduire)),
            "total_primes": Decimal(str(total_primes)),
            "autres_paiements": Decimal(str(total_primes)),
            "total_frais": Decimal(str(total_frais)),
            "quinzaine": quinzaine_rec,
            "solde": solde_rec,
            "total_mois": total_mois,
            "reste_du": Decimal(str(reste_du_total)),
            "alertes": alertes,
        })

    return lignes


def get_total_mensuel(mois: int, annee: int) -> Decimal:
    """
    Total net affiché dans le livre de paie.
    Les avances/crédits ne sont pas ajoutés ici : ils sont déduits du solde.
    """
    operations_net = (
        AvanceSalaire.query
        .filter(
            AvanceSalaire.mois == mois,
            AvanceSalaire.annee == annee,
            AvanceSalaire.type.in_(["prime", "tache", "cumul", "reste_du"]),
        )
        .with_entities(func.sum(AvanceSalaire.montant))
        .scalar() or 0
    )
    salaires = (
        Salaire.query
        .filter_by(mois=mois, annee=annee)
        .with_entities(func.sum(Salaire.montant_net_paye))
        .scalar() or 0
    )
    return Decimal(str(operations_net)) + Decimal(str(salaires))


def get_alertes_fin_mois(mois: int, annee: int) -> list[dict]:
    """
    Retourne la liste des alertes actives pour le mois :
    - employés à salaire fixe sans solde fin de mois
    - restes dûs non soldés
    """
    alertes = []
    employes_fixes = Employe.query.filter(
        Employe.actif == True,
        Employe.type_remuneration.in_(["salaire_fixe", "mixte"]),
    ).all()

    for emp in employes_fixes:
        if not a_salaire_fin_mois(emp.id, mois, annee):
            alertes.append({
                "employe": emp,
                "type": "solde_fin_mois_non_paye",
                "message": f"{emp.nom_complet} — solde fin de mois non payé",
            })

    # Restes dûs actifs
    restes = (
        AvanceSalaire.query
        .filter(
            AvanceSalaire.mois == mois,
            AvanceSalaire.annee == annee,
            AvanceSalaire.type.in_(["tache", "reste_du"]),
            AvanceSalaire.reste_du.isnot(None),
            AvanceSalaire.reste_du > 0,
        )
        .all()
    )
    for ligne in restes:
        alertes.append({
            "employe": ligne.employe,
            "type": "reste_du",
            "message": f"{ligne.employe.nom_complet} — reste dû : {ligne.reste_du} DH",
            "montant": ligne.reste_du,
        })

    return alertes

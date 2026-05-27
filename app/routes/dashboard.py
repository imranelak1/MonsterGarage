from datetime import date

from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_required

from app.models import DossierReparation, FactureReparation

bp = Blueprint("dashboard", __name__)


GROUPES_FLUX = [
    {
        "titre": "Prise en charge",
        "sous_titre": "Devis initial et accords",
        "statuts": ["pending_devis", "pending_approval"],
        "couleur": "slate",
    },
    {
        "titre": "En mecanique",
        "sous_titre": "Reparation active ou en pause",
        "statuts": ["in_progress", "paused_pending_approval"],
        "couleur": "yellow",
    },
    {
        "titre": "Finition & livraison",
        "sous_titre": "Termine ou pret a facturer",
        "statuts": ["completed", "cancelled_billable"],
        "couleur": "green",
    },
]

PROGRESSION_STATUT = {
    "pending_devis": 15,
    "pending_approval": 30,
    "paused_pending_approval": 55,
    "in_progress": 70,
    "completed": 100,
    "cancelled_billable": 90,
    "cancelled": 0,
}

BADGES_STATUT = {
    "pending_devis": "bg-blue-50 text-blue-700",
    "pending_approval": "bg-amber-50 text-amber-700",
    "paused_pending_approval": "bg-orange-50 text-orange-700",
    "in_progress": "bg-yellow-100 text-slate-950",
    "completed": "bg-emerald-50 text-emerald-700",
    "cancelled_billable": "bg-orange-50 text-orange-700",
    "cancelled": "bg-red-50 text-red-700",
}

PRIORITE_RANG = {
    "urgente": 4,
    "haute": 3,
    "normale": 2,
    "basse": 1,
}


@bp.route("/")
def index():
    return redirect(url_for("dashboard.accueil"))


@bp.route("/tableau-de-bord")
@login_required
def accueil():
    statuts_ouverts = ["pending_devis", "pending_approval", "in_progress", "paused_pending_approval"]
    total_dossiers = DossierReparation.query.count()
    attente_accord = DossierReparation.query.filter_by(statut="pending_approval").count()
    en_reparation = DossierReparation.query.filter(
        DossierReparation.statut.in_(["in_progress", "paused_pending_approval"])
    ).count()
    factures_a_suivre = FactureReparation.query.filter(FactureReparation.statut.in_(["emise", "livree"])).count()
    dossiers_en_retard = DossierReparation.query.filter(
        DossierReparation.date_promesse < date.today(),
        DossierReparation.statut.in_(statuts_ouverts),
    ).count()

    indicateurs = [
        {"libelle": "Dossiers atelier", "valeur": total_dossiers, "detail": "Flux complet"},
        {"libelle": "Devis en attente", "valeur": attente_accord, "detail": "Accord client"},
        {"libelle": "En reparation", "valeur": en_reparation, "detail": "Actif ou pause"},
        {"libelle": "Retards", "valeur": dossiers_en_retard, "detail": "Date promise depassee"},
        {"libelle": "Livraison / reglement", "valeur": factures_a_suivre, "detail": "Factures a suivre"},
    ]

    colonnes = []
    for groupe in GROUPES_FLUX:
        dossiers = (
            DossierReparation.query.filter(DossierReparation.statut.in_(groupe["statuts"]))
            .order_by(DossierReparation.date_promesse.is_(None), DossierReparation.date_promesse.asc(), DossierReparation.updated_at.desc())
            .limit(12)
            .all()
        )
        dossiers.sort(key=lambda dossier: PRIORITE_RANG.get(dossier.priorite, 2), reverse=True)
        colonnes.append({**groupe, "dossiers": dossiers[:5]})

    dernier_dossier = DossierReparation.query.order_by(DossierReparation.created_at.desc()).first()

    return render_template(
        "dashboard/accueil.html",
        indicateurs=indicateurs,
        colonnes=colonnes,
        dernier_dossier=dernier_dossier,
        progressions=PROGRESSION_STATUT,
        badges=BADGES_STATUT,
    )

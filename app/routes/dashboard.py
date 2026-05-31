from datetime import date
from decimal import Decimal

from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Client, DossierReparation, EntreeChiffreAffaires, FactureReparation

bp = Blueprint("dashboard", __name__)


GROUPES_FLUX = [
    {
        "titre": "Prise en charge",
        "sous_titre": "Devis initial et accords",
        "statuts": ["pending_devis", "pending_approval"],
        "couleur": "slate",
    },
    {
        "titre": "En mécanique",
        "sous_titre": "Réparation active ou en pause",
        "statuts": ["in_progress", "paused_pending_approval"],
        "couleur": "yellow",
    },
    {
        "titre": "Finition & livraison",
        "sous_titre": "Terminé ou prêt à facturer",
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


@bp.route("/")
def index():
    return redirect(url_for("dashboard.accueil"))


@bp.route("/tableau-de-bord")
@login_required
def accueil():
    aujourd_hui = date.today()
    ca_mois = (
        db.session.query(db.func.coalesce(db.func.sum(EntreeChiffreAffaires.montant), 0))
        .filter(
            db.extract("year", EntreeChiffreAffaires.date) == aujourd_hui.year,
            db.extract("month", EntreeChiffreAffaires.date) == aujourd_hui.month,
        )
        .scalar()
    )
    ca_mois = Decimal(str(ca_mois or 0)).quantize(Decimal("0.01"))
    dossiers_atelier = DossierReparation.query.join(DossierReparation.client).filter(Client.type != "sntl")
    total_dossiers = dossiers_atelier.count()
    dossiers_sntl = DossierReparation.query.join(DossierReparation.client).filter(Client.type == "sntl").count()
    attente_accord = dossiers_atelier.filter(DossierReparation.statut == "pending_approval").count()
    en_reparation = dossiers_atelier.filter(DossierReparation.statut.in_(["in_progress", "paused_pending_approval"])).count()
    factures_a_suivre = FactureReparation.query.filter(FactureReparation.statut.in_(["emise", "livree"])).count()

    indicateurs = [
        {"libelle": "CA manuel du mois", "valeur": f"{ca_mois:,.2f} MAD".replace(",", " "), "detail": "Saisie gerant"},
        {"libelle": "Dossiers atelier", "valeur": total_dossiers, "detail": "Flux complet"},
        {"libelle": "Dossiers SNTL", "valeur": dossiers_sntl, "detail": "Module dedie"},
        {"libelle": "Devis en attente", "valeur": attente_accord, "detail": "Accord client"},
        {"libelle": "En réparation", "valeur": en_reparation, "detail": "Actif ou pause"},
        {"libelle": "Livraison / règlement", "valeur": factures_a_suivre, "detail": "Factures à suivre"},
    ]

    colonnes = []
    for groupe in GROUPES_FLUX:
        dossiers = (
            DossierReparation.query.join(DossierReparation.client)
            .filter(Client.type != "sntl", DossierReparation.statut.in_(groupe["statuts"]))
            .order_by(DossierReparation.updated_at.desc())
            .limit(5)
            .all()
        )
        colonnes.append({**groupe, "dossiers": dossiers})

    dernier_dossier = DossierReparation.query.order_by(DossierReparation.created_at.desc()).first()

    return render_template(
        "dashboard/accueil.html",
        indicateurs=indicateurs,
        colonnes=colonnes,
        dernier_dossier=dernier_dossier,
        progressions=PROGRESSION_STATUT,
        badges=BADGES_STATUT,
    )

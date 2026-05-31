from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload

from app.models import Client, DossierReparation, Vehicule
from app.services.pagination import paginer

bp = Blueprint("vehicules", __name__, url_prefix="/vehicules")


@bp.route("/")
@login_required
def liste():
    recherche = request.args.get("q", "").strip()
    type_vehicule = request.args.get("type", "").strip()
    requete = Vehicule.query.join(Client)

    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            or_(
                Vehicule.immatriculation.ilike(motif),
                Vehicule.marque.ilike(motif),
                Vehicule.modele.ilike(motif),
                Vehicule.vin.ilike(motif),
                Client.nom.ilike(motif),
            )
        )
    if type_vehicule in {"voiture", "utilitaire", "camion", "moto", "engin", "bateau"}:
        requete = requete.filter(Vehicule.type_vehicule == type_vehicule)

    requete = requete.options(
        joinedload(Vehicule.client),
        selectinload(Vehicule.dossiers_reparation),
    )
    pagination = paginer(requete.order_by(Vehicule.created_at.desc()))
    vehicules = pagination.items
    statuts_ouverts = {"pending_devis", "pending_approval", "in_progress", "paused_pending_approval"}
    resumes = []
    for vehicule in vehicules:
        dossiers = list(getattr(vehicule, "dossiers_reparation", []))
        dossier_actif = next((dossier for dossier in sorted(dossiers, key=lambda item: item.created_at, reverse=True) if dossier.statut in statuts_ouverts), None)
        dernier_dossier = max(dossiers, key=lambda dossier: dossier.created_at) if dossiers else None
        resumes.append({
            "vehicule": vehicule,
            "dossiers_count": len(dossiers),
            "dossier_actif": dossier_actif,
            "dernier_dossier": dernier_dossier,
        })

    stats = {
        "total": Vehicule.query.count(),
        "en_atelier": DossierReparation.query.filter(DossierReparation.statut.in_(statuts_ouverts)).with_entities(DossierReparation.vehicule_id).distinct().count(),
        "clients": Client.query.count(),
        "voitures": Vehicule.query.filter_by(type_vehicule="voiture").count(),
    }
    return render_template(
        "vehicules/liste.html",
        vehicules=vehicules,
        pagination=pagination,
        resumes=resumes,
        stats=stats,
        recherche=recherche,
        type_vehicule=type_vehicule,
    )

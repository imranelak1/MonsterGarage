from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import EntreeChiffreAffaires
from app.security import admin_required
from app.services.chiffre_affaires import SOURCES_CA, decimal_montant_ca
from app.services.date_filters import periode_depuis_requete
from app.services.pagination import paginer

bp = Blueprint("chiffre_affaires", __name__, url_prefix="/ca")


@bp.route("/", methods=["GET", "POST"])
@admin_required
def liste():
    if request.method == "POST":
        try:
            entree = _entree_depuis_formulaire()
        except ValueError as erreur:
            flash(str(erreur), "danger")
            return redirect(url_for("chiffre_affaires.liste"))

        db.session.add(entree)
        db.session.commit()
        flash("Entree de chiffre d'affaires enregistree.", "success")
        return redirect(url_for("chiffre_affaires.liste", date_debut=entree.date.isoformat(), date_fin=entree.date.isoformat()))

    source = request.args.get("source", "").strip()
    periode = periode_depuis_requete()
    requete = EntreeChiffreAffaires.query

    if source in SOURCES_CA:
        requete = requete.filter(EntreeChiffreAffaires.source == source)
    if periode.debut:
        requete = requete.filter(EntreeChiffreAffaires.date >= periode.debut)
    if periode.fin:
        requete = requete.filter(EntreeChiffreAffaires.date <= periode.fin)

    total_periode = _total(requete)
    aujourd_hui = date.today()
    total_mois = _total(
        EntreeChiffreAffaires.query.filter(
            db.extract("year", EntreeChiffreAffaires.date) == aujourd_hui.year,
            db.extract("month", EntreeChiffreAffaires.date) == aujourd_hui.month,
        )
    )
    totaux_sources = {
        cle: _total(requete.filter(EntreeChiffreAffaires.source == cle))
        for cle in SOURCES_CA
    }
    pagination = paginer(requete.order_by(EntreeChiffreAffaires.date.desc(), EntreeChiffreAffaires.created_at.desc()))

    return render_template(
        "chiffre_affaires/liste.html",
        entrees=pagination.items,
        pagination=pagination,
        periode=periode,
        source=source,
        sources=SOURCES_CA,
        total_periode=total_periode,
        total_mois=total_mois,
        totaux_sources=totaux_sources,
        aujourd_hui=aujourd_hui,
    )


@bp.route("/<int:entree_id>/supprimer", methods=["POST"])
@admin_required
def supprimer(entree_id):
    entree = db.session.get(EntreeChiffreAffaires, entree_id)
    if not entree:
        flash("Entree de CA introuvable.", "warning")
        return redirect(url_for("chiffre_affaires.liste"))

    db.session.delete(entree)
    db.session.commit()
    flash("Entree de CA supprimee.", "success")
    return redirect(url_for("chiffre_affaires.liste"))


def _entree_depuis_formulaire() -> EntreeChiffreAffaires:
    date_valeur = request.form.get("date", "").strip()
    try:
        date_ca = date.fromisoformat(date_valeur)
    except ValueError:
        raise ValueError("Selectionnez une date de CA valide.") from None

    source = request.form.get("source", "atelier").strip()
    if source not in SOURCES_CA:
        raise ValueError("Selectionnez une source de CA valide.")

    libelle = request.form.get("libelle", "").strip()
    if not libelle:
        raise ValueError("Le libelle de l'entree CA est obligatoire.")

    return EntreeChiffreAffaires(
        date=date_ca,
        montant=decimal_montant_ca(request.form.get("montant")),
        source=source,
        libelle=libelle,
        notes=request.form.get("notes", "").strip(),
        created_by_id=current_user.id,
    )


def _total(requete) -> Decimal:
    total = requete.with_entities(db.func.coalesce(db.func.sum(EntreeChiffreAffaires.montant), 0)).scalar()
    return Decimal(str(total or 0)).quantize(Decimal("0.01"))

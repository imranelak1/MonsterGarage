from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Client, DossierReparation, FactureReparation
from app.services.dossiers import RegleMetierErreur
from app.services.export_documents import (
    XLSX_MIMETYPE,
    exporter_facture_excel,
    exporter_releve_client_excel,
    nom_fichier_facture,
    nom_fichier_releve_client,
)
from app.services.factures import enregistrer_reglement, generer_facture, marquer_livree

bp = Blueprint("factures", __name__, url_prefix="/factures")


@bp.route("/")
@login_required
def liste():
    statut = request.args.get("statut", "").strip()
    requete = FactureReparation.query
    if statut:
        requete = requete.filter_by(statut=statut)
    factures = requete.order_by(FactureReparation.created_at.desc()).limit(100).all()
    return render_template("factures/liste.html", factures=factures, statut=statut)


@bp.route("/<int:facture_id>")
@login_required
def detail(facture_id):
    facture = db.session.get(FactureReparation, facture_id)
    if not facture:
        flash("Facture introuvable.", "warning")
        return redirect(url_for("factures.liste"))
    return render_template("factures/detail.html", facture=facture)


@bp.route("/<int:facture_id>/telecharger")
@login_required
def telecharger(facture_id):
    facture = db.session.get(FactureReparation, facture_id)
    if not facture:
        flash("Facture introuvable.", "warning")
        return redirect(url_for("factures.liste"))

    data = exporter_facture_excel(facture)
    filename = nom_fichier_facture(facture)
    return Response(
        data,
        mimetype=XLSX_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/clients/<int:client_id>/releve")
@login_required
def releve_client(client_id):
    client_db = db.session.get(Client, client_id)
    if not client_db:
        flash("Client introuvable.", "warning")
        return redirect(url_for("factures.liste"))

    factures = (
        FactureReparation.query.join(FactureReparation.dossier)
        .filter(DossierReparation.client_id == client_db.id)
        .order_by(FactureReparation.created_at.asc())
        .all()
    )
    data = exporter_releve_client_excel(client_db, factures)
    filename = nom_fichier_releve_client(client_db)
    return Response(
        data,
        mimetype=XLSX_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/dossiers/<int:dossier_id>/generer", methods=["POST"])
@login_required
def generer_depuis_dossier(dossier_id):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier atelier introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        facture = generer_facture(dossier)
        db.session.commit()
        flash("Facture finale générée depuis le dernier devis approuvé.", "success")
        return redirect(url_for("factures.detail", facture_id=facture.id))
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")
        return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:facture_id>/livrer", methods=["POST"])
@login_required
def livrer(facture_id):
    facture = db.session.get(FactureReparation, facture_id)
    if not facture:
        flash("Facture introuvable.", "warning")
        return redirect(url_for("factures.liste"))

    try:
        marquer_livree(facture)
        db.session.commit()
        flash("Livraison enregistrée. Vous pouvez maintenant saisir le règlement.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("factures.detail", facture_id=facture.id))


@bp.route("/<int:facture_id>/regler", methods=["POST"])
@login_required
def regler(facture_id):
    facture = db.session.get(FactureReparation, facture_id)
    if not facture:
        flash("Facture introuvable.", "warning")
        return redirect(url_for("factures.liste"))

    try:
        enregistrer_reglement(
            facture,
            mode_reglement=request.form.get("mode_reglement", "especes"),
            montant=request.form.get("montant_reglement", ""),
            reference=request.form.get("reference_reglement", ""),
        )
        db.session.commit()
        flash("Règlement enregistré. Le flux dossier est clôturé.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("factures.detail", facture_id=facture.id))

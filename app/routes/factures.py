from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Client, DossierReparation, FactureReparation
from app.services.date_filters import appliquer_filtre_periode, periode_depuis_requete
from app.services.dossiers import RegleMetierErreur
from app.services.export_documents import (
    XLSX_MIMETYPE,
    exporter_facture_excel,
    exporter_releve_client_excel,
    exporter_situation_clients_excel,
    nom_fichier_facture,
    nom_fichier_releve_client,
)
from app.services.export_pdf import PDF_MIMETYPE, exporter_facture_pdf, nom_fichier_facture_pdf
from app.services.factures import enregistrer_reglement, generer_facture, marquer_livree
from app.services.pagination import paginer

bp = Blueprint("factures", __name__, url_prefix="/factures")


@bp.route("/")
@login_required
def liste():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    periode = periode_depuis_requete()
    requete = FactureReparation.query
    if statut:
        requete = requete.filter_by(statut=statut)
    requete = (
        requete
        .join(FactureReparation.dossier)
        .join(DossierReparation.client)
        .join(DossierReparation.vehicule)
    )
    requete = appliquer_filtre_periode(requete, FactureReparation.created_at, periode)
    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            db.or_(
                FactureReparation.numero.ilike(motif),
                DossierReparation.numero.ilike(motif),
                Client.nom.ilike(motif),
                Client.code.ilike(motif),
            )
        )
    requete = requete.options(
        joinedload(FactureReparation.dossier).joinedload(DossierReparation.client),
        joinedload(FactureReparation.dossier).joinedload(DossierReparation.vehicule),
    )
    pagination = paginer(requete.order_by(FactureReparation.created_at.desc()))
    return render_template("factures/liste.html", factures=pagination.items, pagination=pagination, statut=statut, recherche=recherche, periode=periode)


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


@bp.route("/<int:facture_id>/pdf")
@login_required
def voir_pdf(facture_id):
    return _reponse_facture_pdf(facture_id, telechargement=False)


@bp.route("/<int:facture_id>/pdf/telecharger")
@login_required
def telecharger_pdf(facture_id):
    return _reponse_facture_pdf(facture_id, telechargement=True)


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


@bp.route("/clients/situation-financiere")
@login_required
def situation_financiere_clients():
    return _situation_financiere_clients()


@bp.route("/clients/situation-financiere/particuliers")
@login_required
def situation_financiere_particuliers():
    return _situation_financiere_clients(type_client="particuliers")


@bp.route("/clients/situation-financiere/sntl")
@login_required
def situation_financiere_sntl():
    return _situation_financiere_clients(type_client="sntl")


def _situation_financiere_clients(type_client: str | None = None):
    factures = (
        FactureReparation.query.join(FactureReparation.dossier)
        .join(DossierReparation.client)
        .filter(FactureReparation.statut != "annulee")
    )
    if type_client == "sntl":
        factures = factures.filter(Client.type == "sntl")
        filename = "SITUATION_FINANCIERE_SNTL.xlsx"
    elif type_client == "particuliers":
        factures = factures.filter(Client.type != "sntl")
        filename = "SITUATION_FINANCIERE_PARTICULIERS.xlsx"
    else:
        filename = "SITUATION_FINANCIERE_CLIENTS.xlsx"
    factures = factures.order_by(Client.nom.asc(), FactureReparation.created_at.asc()).all()
    client_ids = []
    clients_par_id = {}
    for facture in factures:
        client_db = facture.dossier.client
        if client_db.id not in clients_par_id:
            clients_par_id[client_db.id] = client_db
            client_ids.append(client_db.id)

    clients = [clients_par_id[client_id] for client_id in client_ids]
    data = exporter_situation_clients_excel(clients, factures)
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


def _reponse_facture_pdf(facture_id: int, *, telechargement: bool):
    facture = db.session.get(FactureReparation, facture_id)
    if not facture:
        flash("Facture introuvable.", "warning")
        return redirect(url_for("factures.liste"))

    filename = nom_fichier_facture_pdf(facture)
    disposition = "attachment" if telechargement else "inline"
    return Response(
        exporter_facture_pdf(facture),
        mimetype=PDF_MIMETYPE,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )

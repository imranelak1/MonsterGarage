from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Client, DossierReparation, Vehicule
from app.services.date_filters import appliquer_filtre_periode, periode_depuis_requete
from app.services.pagination import paginer
from app.services.telephone import normaliser_telephone

bp = Blueprint("clients", __name__, url_prefix="/clients")


@bp.route("/")
@login_required
def liste():
    recherche = request.args.get("q", "").strip()
    type_client = request.args.get("type", "").strip()
    periode = periode_depuis_requete()
    requete = Client.query

    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            or_(
                Client.code.ilike(motif),
                Client.nom.ilike(motif),
                Client.sigle.ilike(motif),
                Client.telephone.ilike(motif),
                Client.ice.ilike(motif),
            )
        )
    if type_client in {"particulier", "administration", "sntl"}:
        requete = requete.filter(Client.type == type_client)
    requete = appliquer_filtre_periode(requete, Client.created_at, periode)

    requete = requete.options(
        selectinload(Client.vehicules),
        selectinload(Client.dossiers_reparation),
    )
    pagination = paginer(requete.order_by(Client.created_at.desc()))
    clients = pagination.items
    statuts_ouverts = {"pending_devis", "pending_approval", "in_progress", "paused_pending_approval"}
    resumes = []
    for client in clients:
        dossiers = list(getattr(client, "dossiers_reparation", []))
        dossiers_ouverts = [dossier for dossier in dossiers if dossier.statut in statuts_ouverts]
        dernier_dossier = max(dossiers, key=lambda dossier: dossier.created_at) if dossiers else None
        resumes.append({
            "client": client,
            "vehicules_count": len(client.vehicules),
            "dossiers_count": len(dossiers),
            "dossiers_ouverts": len(dossiers_ouverts),
            "dernier_dossier": dernier_dossier,
        })

    stats = {
        "total": Client.query.count(),
        "particuliers": Client.query.filter_by(type="particulier").count(),
        "administrations": Client.query.filter_by(type="administration").count(),
        "sntl": Client.query.filter_by(type="sntl").count(),
        "vehicules": Vehicule.query.count(),
        "dossiers_ouverts": DossierReparation.query.filter(DossierReparation.statut.in_(statuts_ouverts)).count(),
    }
    return render_template(
        "clients/liste.html",
        clients=clients,
        pagination=pagination,
        resumes=resumes,
        stats=stats,
        recherche=recherche,
        type_client=type_client,
        periode=periode,
    )


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    if request.method == "POST":
        try:
            telephone = normaliser_telephone(request.form.get("telephone"))
            telephone_2 = normaliser_telephone(request.form.get("telephone_2"))
        except ValueError as erreur:
            flash(str(erreur), "danger")
            return render_template("clients/formulaire.html", client=None)

        client = Client(
            code=request.form.get("code", "").strip(),
            type=request.form.get("type", "particulier"),
            nom=request.form.get("nom", "").strip(),
            sigle=request.form.get("sigle", "").strip(),
            telephone=telephone,
            telephone_2=telephone_2,
            email=request.form.get("email", "").strip(),
            adresse=request.form.get("adresse", "").strip(),
            ville=request.form.get("ville", "").strip(),
            ice=request.form.get("ice", "").strip(),
            if_fiscal=request.form.get("if_fiscal", "").strip(),
            rc=request.form.get("rc", "").strip(),
            administration_rattachee=request.form.get("administration_rattachee", "").strip(),
            delai_paiement_jours=int(request.form.get("delai_paiement_jours") or 30),
            notes=request.form.get("notes", "").strip(),
        )

        if not client.code or not client.nom:
            flash("Le code et le nom du client sont obligatoires.", "danger")
            return render_template("clients/formulaire.html", client=client)

        if Client.query.filter_by(code=client.code).first():
            flash("Ce code client existe déjà.", "danger")
            return render_template("clients/formulaire.html", client=client)

        db.session.add(client)
        db.session.flush()

        immatriculation = request.form.get("immatriculation", "").strip()
        marque = request.form.get("marque", "").strip()
        modele = request.form.get("modele", "").strip()
        if immatriculation or marque or modele:
            if not (immatriculation and marque and modele):
                db.session.rollback()
                flash("Pour ajouter un véhicule, immatriculation, marque et modèle sont obligatoires.", "danger")
                return render_template("clients/formulaire.html", client=client)

            db.session.add(
                Vehicule(
                    client_id=client.id,
                    immatriculation=immatriculation,
                    marque=marque,
                    modele=modele,
                    type_immatriculation=request.form.get("type_immatriculation") or "standard",
                    type_vehicule=request.form.get("type_vehicule") or "voiture",
                    type_carburant=request.form.get("type_carburant") or None,
                    kilometrage_actuel=_int_ou_none(request.form.get("kilometrage_actuel")),
                )
            )

        db.session.commit()
        flash("Client enregistré.", "success")
        return redirect(url_for("clients.detail", client_id=client.id))

    return render_template("clients/formulaire.html", client=None)


@bp.route("/<int:client_id>")
@login_required
def detail(client_id):
    client = db.session.get(Client, client_id)
    if not client:
        flash("Client introuvable.", "warning")
        return redirect(url_for("clients.liste"))

    return render_template("clients/detail.html", client=client)


@bp.route("/<int:client_id>/modifier", methods=["GET", "POST"])
@login_required
def modifier(client_id):
    client = db.session.get(Client, client_id)
    if not client:
        flash("Client introuvable.", "warning")
        return redirect(url_for("clients.liste"))

    retour = request.args.get("retour") or request.form.get("retour") or url_for("clients.detail", client_id=client.id)

    if request.method == "POST":
        try:
            telephone = normaliser_telephone(request.form.get("telephone"))
            telephone_2 = normaliser_telephone(request.form.get("telephone_2"))
        except ValueError as erreur:
            flash(str(erreur), "danger")
            return render_template("clients/formulaire.html", client=client, retour=retour)

        code = request.form.get("code", "").strip()
        nom = request.form.get("nom", "").strip()
        if not code or not nom:
            flash("Le code et le nom du client sont obligatoires.", "danger")
            return render_template("clients/formulaire.html", client=client, retour=retour)

        code_existant = Client.query.filter(Client.code == code, Client.id != client.id).first()
        if code_existant:
            flash("Ce code client existe déjà.", "danger")
            return render_template("clients/formulaire.html", client=client, retour=retour)

        client.code = code
        client.type = request.form.get("type", "particulier")
        client.nom = nom
        client.sigle = request.form.get("sigle", "").strip()
        client.telephone = telephone
        client.telephone_2 = telephone_2
        client.email = request.form.get("email", "").strip()
        client.adresse = request.form.get("adresse", "").strip()
        client.ville = request.form.get("ville", "").strip()
        client.ice = request.form.get("ice", "").strip()
        client.if_fiscal = request.form.get("if_fiscal", "").strip()
        client.rc = request.form.get("rc", "").strip()
        client.administration_rattachee = request.form.get("administration_rattachee", "").strip()
        client.delai_paiement_jours = int(request.form.get("delai_paiement_jours") or 30)
        client.notes = request.form.get("notes", "").strip()

        db.session.commit()
        flash("Client mis à jour.", "success")
        return redirect(retour)

    return render_template("clients/formulaire.html", client=client, retour=retour)


@bp.route("/<int:client_id>/vehicules/nouveau", methods=["POST"])
@login_required
def ajouter_vehicule(client_id):
    client = db.session.get(Client, client_id)
    if not client:
        flash("Client introuvable.", "warning")
        return redirect(url_for("clients.liste"))

    immatriculation = request.form.get("immatriculation", "").strip()
    marque = request.form.get("marque", "").strip()
    modele = request.form.get("modele", "").strip()

    if not (immatriculation and marque and modele):
        flash("Immatriculation, marque et modèle sont obligatoires.", "danger")
        return redirect(url_for("clients.detail", client_id=client.id))

    vehicule = Vehicule(
        client_id=client.id,
        immatriculation=immatriculation,
        marque=marque,
        modele=modele,
        type_immatriculation=request.form.get("type_immatriculation") or "standard",
        type_vehicule=request.form.get("type_vehicule") or "voiture",
        type_carburant=request.form.get("type_carburant") or None,
        kilometrage_actuel=_int_ou_none(request.form.get("kilometrage_actuel")),
    )
    db.session.add(vehicule)
    db.session.commit()

    flash("Véhicule ajouté au client.", "success")
    return redirect(url_for("clients.detail", client_id=client.id))


def _int_ou_none(valeur: str | None) -> int | None:
    if not valeur:
        return None
    try:
        return int(valeur)
    except ValueError:
        return None

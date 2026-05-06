from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Client, Vehicule
from app.services.telephone import normaliser_telephone

bp = Blueprint("clients", __name__, url_prefix="/clients")


@bp.route("/")
@login_required
def liste():
    recherche = request.args.get("q", "").strip()
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

    clients = requete.order_by(Client.created_at.desc()).limit(100).all()
    return render_template("clients/liste.html", clients=clients, recherche=recherche)


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

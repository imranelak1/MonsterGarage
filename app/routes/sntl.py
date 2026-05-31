from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Client, DevisReparation, DossierReparation, Vehicule
from app.services.date_filters import appliquer_filtre_periode, periode_depuis_requete
from app.services.dossiers import (
    RegleMetierErreur,
    approuver_devis,
    creer_devis,
    generer_numero_dossier,
    journaliser,
    terminer_dossier,
)
from app.services.dossiers_sntl import (
    SNTL_CLIENTS_PREDEFINIS,
    assurer_numero_bon_sntl,
    est_dossier_sntl,
    forcer_piece_neuve,
    preset_sntl,
    requete_dossiers_sntl,
)
from app.services.factures import generer_facture
from app.services.pagination import paginer
from app.services.telephone import normaliser_telephone

bp = Blueprint("sntl", __name__, url_prefix="/sntl")


@bp.route("/")
@login_required
def liste():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    periode = periode_depuis_requete()
    requete = requete_dossiers_sntl().join(DossierReparation.vehicule)
    if statut:
        requete = requete.filter(DossierReparation.statut == statut)
    requete = appliquer_filtre_periode(requete, DossierReparation.created_at, periode)
    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            db.or_(
                DossierReparation.numero.ilike(motif),
                DossierReparation.numero_bon_sntl.ilike(motif),
                DossierReparation.demande_client.ilike(motif),
                Client.nom.ilike(motif),
                Client.code.ilike(motif),
                Vehicule.immatriculation.ilike(motif),
                Vehicule.marque.ilike(motif),
                Vehicule.modele.ilike(motif),
            )
        )
    requete = requete.options(
        joinedload(DossierReparation.client),
        joinedload(DossierReparation.vehicule),
    )
    pagination = paginer(requete.order_by(DossierReparation.created_at.desc()))
    return render_template("sntl/liste.html", dossiers=pagination.items, pagination=pagination, statut=statut, recherche=recherche, periode=periode)


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    clients = Client.query.filter_by(type="sntl").order_by(Client.nom.asc()).all()
    vehicules = Vehicule.query.join(Vehicule.client).filter(Client.type == "sntl").order_by(Vehicule.immatriculation.asc()).all()
    client_choices = _choix_clients_sntl(clients)

    if request.method == "POST":
        demande_client = request.form.get("demande_client", "").strip()
        if not demande_client:
            flash("La demande SNTL est obligatoire.", "danger")
            return render_template("sntl/nouveau.html", clients=clients, vehicules=vehicules, client_choices=client_choices, sntl_presets=SNTL_CLIENTS_PREDEFINIS)

        try:
            client = _obtenir_ou_creer_client_sntl()
            db.session.flush()
            vehicule = _obtenir_ou_creer_vehicule_sntl(client)
            db.session.flush()
            dossier = DossierReparation(
                numero=generer_numero_dossier(),
                client_id=client.id,
                vehicule_id=vehicule.id,
                created_by_id=current_user.id,
                demande_client=demande_client,
                diagnostic_initial=request.form.get("diagnostic_initial", "").strip(),
                assurance_nom="",
                numero_bon_sntl=assurer_numero_bon_sntl(request.form.get("numero_bon_sntl")),
                kilometrage_entree=_int_ou_none(request.form.get("kilometrage_entree")),
                notes=request.form.get("notes", "").strip(),
            )
            db.session.add(dossier)
            db.session.flush()
            journaliser(dossier, "dossier_sntl_cree", "Dossier SNTL cree depuis le module SNTL.")
            db.session.commit()
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return render_template("sntl/nouveau.html", clients=clients, vehicules=vehicules, client_choices=client_choices, sntl_presets=SNTL_CLIENTS_PREDEFINIS)

        flash("Dossier SNTL cree. Prochaine etape : devis SNTL.", "success")
        return redirect(url_for("sntl.detail", dossier_id=dossier.id))

    return render_template("sntl/nouveau.html", clients=clients, vehicules=vehicules, client_choices=client_choices, sntl_presets=SNTL_CLIENTS_PREDEFINIS)


@bp.route("/<int:dossier_id>")
@login_required
def detail(dossier_id):
    dossier = _obtenir_dossier_sntl(dossier_id)
    if not dossier:
        return redirect(url_for("sntl.liste"))
    return render_template("sntl/detail.html", dossier=dossier)


@bp.route("/<int:dossier_id>/devis/nouveau", methods=["GET", "POST"])
@login_required
def nouveau_devis(dossier_id):
    dossier = _obtenir_dossier_sntl(dossier_id)
    if not dossier:
        return redirect(url_for("sntl.liste"))

    if request.method == "POST":
        try:
            creer_devis(
                dossier,
                objet=request.form.get("objet", ""),
                lignes_formulaire=_lignes_devis_depuis_formulaire(),
                notes=request.form.get("notes", ""),
            )
            db.session.commit()
            flash("Devis SNTL cree et en attente d'accord.", "success")
            return redirect(url_for("sntl.detail", dossier_id=dossier.id))
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")

    return render_template("dossiers/devis_formulaire.html", dossier=dossier)


@bp.route("/devis/<int:devis_id>/approuver", methods=["POST"])
@login_required
def approuver(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis or not est_dossier_sntl(devis.dossier):
        flash("Devis SNTL introuvable.", "warning")
        return redirect(url_for("sntl.liste"))

    try:
        approuver_devis(devis, mode_accord=request.form.get("mode_accord", "telephone"))
        db.session.commit()
        flash("Accord SNTL enregistre. Le dossier passe en reparation.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("sntl.detail", dossier_id=devis.dossier_id))


@bp.route("/<int:dossier_id>/terminer", methods=["POST"])
@login_required
def terminer(dossier_id):
    dossier = _obtenir_dossier_sntl(dossier_id)
    if not dossier:
        return redirect(url_for("sntl.liste"))

    try:
        terminer_dossier(dossier)
        db.session.commit()
        flash("Dossier SNTL termine. La facture SNTL peut etre generee.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("sntl.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/facturer", methods=["POST"])
@login_required
def facturer(dossier_id):
    dossier = _obtenir_dossier_sntl(dossier_id)
    if not dossier:
        return redirect(url_for("sntl.liste"))

    try:
        facture = generer_facture(dossier)
        db.session.commit()
        flash("Facture SNTL generee depuis le dernier devis approuve.", "success")
        return redirect(url_for("factures.detail", facture_id=facture.id))
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")
        return redirect(url_for("sntl.detail", dossier_id=dossier.id))


@bp.route("/releves")
@login_required
def releves():
    return redirect(url_for("factures.situation_financiere_clients"))


def _obtenir_dossier_sntl(dossier_id: int):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier SNTL introuvable.", "warning")
        return None
    if not est_dossier_sntl(dossier):
        flash("Ce dossier n'appartient pas au module SNTL.", "warning")
        return None
    return dossier


def _obtenir_ou_creer_client_sntl() -> Client:
    choix = request.form.get("sntl_client_choice", "").strip()
    if choix:
        if choix.startswith("existing:"):
            client_id = choix.split(":", 1)[1]
            client = db.session.get(Client, int(client_id)) if client_id else None
            if not client or client.type != "sntl":
                raise RegleMetierErreur("Selectionnez une administration SNTL existante.")
            return client
        if choix.startswith("preset:"):
            return _client_depuis_preset_sntl(choix.split(":", 1)[1])
        if choix == "custom":
            return _creer_client_sntl_personnalise()
        raise RegleMetierErreur("Selectionnez une administration SNTL.")

    mode_client = request.form.get("mode_client", "nouveau")
    if mode_client == "existant":
        client_id = request.form.get("client_id")
        client = db.session.get(Client, int(client_id)) if client_id else None
        if not client or client.type != "sntl":
            raise RegleMetierErreur("Selectionnez un client SNTL existant.")
        return client

    preset_key = request.form.get("client_sntl_preset", "").strip()
    if preset_key and preset_key != "custom":
        return _client_depuis_preset_sntl(preset_key)

    return _creer_client_sntl_personnalise()


def _client_depuis_preset_sntl(preset_key: str) -> Client:
    preset = preset_sntl(preset_key)
    client_existant = Client.query.filter_by(code=preset["code"]).first()
    if client_existant:
        return client_existant
    client = Client(
        code=preset["code"],
        type="sntl",
        nom=preset["nom"],
        sigle=preset["nom"].upper(),
        telephone=_telephone_ou_vide(request.form.get("client_telephone")),
        email=request.form.get("client_email", "").strip(),
        adresse=request.form.get("client_adresse", "").strip(),
        ville=request.form.get("client_ville", "").strip() or "Marrakech",
        ice=request.form.get("client_ice", "").strip(),
        administration_rattachee=preset["nom"],
        notes=f"OR numero {preset['or_numero']}",
        delai_paiement_jours=_int_ou_none(request.form.get("client_delai_paiement_jours")) or 30,
    )
    db.session.add(client)
    return client


def _creer_client_sntl_personnalise() -> Client:
    nom = request.form.get("client_nom", "").strip()
    if not nom:
        raise RegleMetierErreur("Le nom de l'administration SNTL est obligatoire.")
    code = request.form.get("client_code", "").strip() or _generer_code_sntl()
    if Client.query.filter_by(code=code).first():
        raise RegleMetierErreur("Ce code client existe deja.")
    client = Client(
        code=code,
        type="sntl",
        nom=nom,
        sigle=request.form.get("client_sigle", "").strip() or nom.upper(),
        telephone=_telephone_ou_vide(request.form.get("client_telephone")),
        email=request.form.get("client_email", "").strip(),
        adresse=request.form.get("client_adresse", "").strip(),
        ville=request.form.get("client_ville", "").strip() or "Marrakech",
        ice=request.form.get("client_ice", "").strip(),
        administration_rattachee=request.form.get("client_administration_rattachee", "").strip() or nom,
        delai_paiement_jours=_int_ou_none(request.form.get("client_delai_paiement_jours")) or 30,
    )
    db.session.add(client)
    return client


def _obtenir_ou_creer_vehicule_sntl(client: Client) -> Vehicule:
    choix = request.form.get("sntl_vehicle_choice", "").strip()
    if choix.startswith("existing:"):
        vehicule_id = choix.split(":", 1)[1]
        vehicule = db.session.get(Vehicule, int(vehicule_id)) if vehicule_id else None
        if not vehicule or vehicule.client_id != client.id:
            raise RegleMetierErreur("Selectionnez un vehicule SNTL coherent avec l'administration.")
        vehicule.type_immatriculation = "administrative"
        return vehicule
    if choix and choix != "new":
        raise RegleMetierErreur("Selectionnez un vehicule SNTL valide.")

    mode_vehicule = request.form.get("mode_vehicule", "nouveau")
    if mode_vehicule == "existant":
        vehicule_id = request.form.get("vehicule_id")
        vehicule = db.session.get(Vehicule, int(vehicule_id)) if vehicule_id else None
        if not vehicule or vehicule.client_id != client.id:
            raise RegleMetierErreur("Selectionnez un vehicule SNTL coherent avec le client.")
        vehicule.type_immatriculation = "administrative"
        return vehicule

    immatriculation = request.form.get("vehicule_immatriculation", "").strip()
    marque = request.form.get("vehicule_marque", "").strip()
    modele = request.form.get("vehicule_modele", "").strip()
    if not (immatriculation and marque and modele):
        raise RegleMetierErreur("Immatriculation, marque et modele sont obligatoires pour ouvrir le dossier SNTL.")
    vehicule = Vehicule(
        client_id=client.id,
        immatriculation=immatriculation,
        marque=marque,
        modele=modele,
        type_immatriculation="administrative",
        type_vehicule=request.form.get("vehicule_type") or "utilitaire",
        type_carburant=request.form.get("vehicule_carburant") or None,
        kilometrage_actuel=_int_ou_none(request.form.get("kilometrage_entree")),
    )
    db.session.add(vehicule)
    return vehicule


def _choix_clients_sntl(clients: list[Client]) -> list[dict]:
    clients_par_code = {client.code: client for client in clients if client.code}
    choix = [
        {
            "value": f"existing:{client.id}",
            "label": f"{client.code} - {client.nom}",
            "kind": "Existant",
            "client_id": client.id,
        }
        for client in clients
    ]
    for key, preset in SNTL_CLIENTS_PREDEFINIS.items():
        if preset["code"] in clients_par_code:
            continue
        choix.append(
            {
                "value": f"preset:{key}",
                "label": f"{preset['code']} - {preset['nom']} / OR {preset['or_numero']}",
                "kind": "Modele",
                "client_id": "",
            }
        )
    return choix


def _lignes_devis_depuis_formulaire() -> list[dict]:
    designations = request.form.getlist("designation")
    if designations:
        quantites = request.form.getlist("quantite")
        prix = request.form.getlist("prix_unitaire_ht")
        return [
            {
                "designation": designation,
                "quantite": quantites[index] if index < len(quantites) else "1",
                "prix_unitaire_ht": prix[index] if index < len(prix) else "0",
                "etat_piece": forcer_piece_neuve(),
            }
            for index, designation in enumerate(designations)
        ]

    return [
        {
            "designation": request.form.get(f"designation_{index}", ""),
            "quantite": request.form.get(f"quantite_{index}", "1"),
            "prix_unitaire_ht": request.form.get(f"prix_unitaire_ht_{index}", "0"),
            "etat_piece": forcer_piece_neuve(),
        }
        for index in range(1, 6)
    ]


def _generer_code_sntl() -> str:
    dernier_id = db.session.query(db.func.max(Client.id)).scalar() or 0
    return f"S{dernier_id + 1:04d}"


def _telephone_ou_vide(valeur: str | None) -> str:
    try:
        return normaliser_telephone(valeur)
    except ValueError as exc:
        raise RegleMetierErreur(str(exc)) from exc


def _int_ou_none(valeur: str | None) -> int | None:
    if not valeur:
        return None
    try:
        return int(valeur)
    except ValueError:
        return None

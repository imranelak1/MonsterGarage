from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Client, DevisReparation, DossierReparation, Vehicule
from app.services.dossiers import (
    RegleMetierErreur,
    annuler_dossier_facturable,
    annuler_dossier,
    approuver_devis,
    creer_devis,
    normaliser_numero_bon_sntl,
    generer_numero_dossier,
    journaliser,
    mettre_en_pause,
    refuser_devis,
    rouvrir_garantie,
    terminer_dossier,
)
from app.services.export_documents import XLSX_MIMETYPE, exporter_devis_excel, nom_fichier_devis
from app.services.export_pdf import PDF_MIMETYPE, exporter_devis_pdf, nom_fichier_devis_pdf
from app.services.telephone import normaliser_telephone

bp = Blueprint("dossiers", __name__, url_prefix="/dossiers")

SNTL_CLIENTS_PREDEFINIS = {
    "600-85": {"code": "600", "nom": "Commune Harbil", "or_numero": "85"},
    "100-83": {"code": "100", "nom": "Wilaya", "or_numero": "83"},
    "300-84": {"code": "300", "nom": "NARSA", "or_numero": "84"},
    "800-89": {"code": "800", "nom": "AMEE", "or_numero": "89"},
}


@bp.route("/")
@login_required
def liste():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    requete = DossierReparation.query.join(DossierReparation.client).join(DossierReparation.vehicule)
    if statut:
        requete = requete.filter(DossierReparation.statut == statut)
    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            db.or_(
                DossierReparation.numero.ilike(motif),
                DossierReparation.demande_client.ilike(motif),
                Client.nom.ilike(motif),
                Client.code.ilike(motif),
                Vehicule.immatriculation.ilike(motif),
                Vehicule.marque.ilike(motif),
                Vehicule.modele.ilike(motif),
            )
        )
    dossiers = requete.order_by(DossierReparation.created_at.desc()).limit(100).all()
    return render_template("dossiers/liste.html", dossiers=dossiers, statut=statut, recherche=recherche)


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    clients = Client.query.order_by(Client.nom.asc()).all()
    vehicules = Vehicule.query.order_by(Vehicule.immatriculation.asc()).all()

    if request.method == "POST":
        demande_client = request.form.get("demande_client", "").strip()
        if not demande_client:
            flash("La demande client est obligatoire.", "danger")
            return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules, sntl_presets=SNTL_CLIENTS_PREDEFINIS)

        try:
            client = _obtenir_ou_creer_client()
            db.session.flush()
            vehicule = _obtenir_ou_creer_vehicule(client)
            db.session.flush()
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules, sntl_presets=SNTL_CLIENTS_PREDEFINIS)

        try:
            numero_bon_sntl = (
                normaliser_numero_bon_sntl(request.form.get("numero_bon_sntl"))
                if client.type == "sntl"
                else request.form.get("numero_bon_sntl", "").strip()
            )
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules, sntl_presets=SNTL_CLIENTS_PREDEFINIS)

        dossier = DossierReparation(
            numero=generer_numero_dossier(),
            client_id=client.id,
            vehicule_id=vehicule.id,
            created_by_id=current_user.id,
            demande_client=demande_client,
            diagnostic_initial=request.form.get("diagnostic_initial", "").strip(),
            assurance_nom=request.form.get("assurance_nom", "").strip() if client.type == "particulier" else "",
            numero_bon_sntl=numero_bon_sntl,
            kilometrage_entree=_int_ou_none(request.form.get("kilometrage_entree")),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(dossier)
        db.session.flush()
        journaliser(dossier, "dossier_cree", "Dossier atelier créé par l'équipe.")
        db.session.commit()

        flash("Dossier atelier créé. Prochaine étape : devis initial.", "success")
        return redirect(url_for("dossiers.detail", dossier_id=dossier.id))

    return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules, sntl_presets=SNTL_CLIENTS_PREDEFINIS)


@bp.route("/<int:dossier_id>")
@login_required
def detail(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))
    return render_template("dossiers/detail.html", dossier=dossier)


@bp.route("/<int:dossier_id>/devis/nouveau", methods=["GET", "POST"])
@login_required
def nouveau_devis(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    if request.method == "POST":
        lignes = _lignes_devis_depuis_formulaire(dossier)

        try:
            creer_devis(
                dossier,
                objet=request.form.get("objet", ""),
                lignes_formulaire=lignes,
                notes=request.form.get("notes", ""),
            )
            db.session.commit()
            flash("Devis créé et envoyé en attente d'accord.", "success")
            return redirect(url_for("dossiers.detail", dossier_id=dossier.id))
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")

    return render_template("dossiers/devis_formulaire.html", dossier=dossier)


@bp.route("/devis/<int:devis_id>/approuver", methods=["POST"])
@login_required
def approuver(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        approuver_devis(
            devis,
            mode_accord=request.form.get("mode_accord", "telephone"),
            accord_assurance=bool(request.form.get("accord_assurance")),
        )
        db.session.commit()
        flash("Accord enregistré. Le dossier peut continuer en réparation.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=devis.dossier_id))


@bp.route("/devis/<int:devis_id>/refuser", methods=["POST"])
@login_required
def refuser(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        refuser_devis(devis, motif=request.form.get("motif_refus", ""))
        db.session.commit()
        flash(
            "Refus enregistré. Créez une version corrigée du devis ou annulez le dossier si le client ne souhaite pas continuer.",
            "warning",
        )
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=devis.dossier_id))


@bp.route("/devis/<int:devis_id>/telecharger")
@login_required
def telecharger_devis(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    data = exporter_devis_excel(devis)
    filename = nom_fichier_devis(devis)
    return Response(
        data,
        mimetype=XLSX_MIMETYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/devis/<int:devis_id>/pdf")
@login_required
def voir_devis_pdf(devis_id):
    return _reponse_devis_pdf(devis_id, telechargement=False)


@bp.route("/devis/<int:devis_id>/pdf/telecharger")
@login_required
def telecharger_devis_pdf(devis_id):
    return _reponse_devis_pdf(devis_id, telechargement=True)


@bp.route("/<int:dossier_id>/pause", methods=["POST"])
@login_required
def pause(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        mettre_en_pause(dossier, request.form.get("raison", ""))
        db.session.commit()
        flash("Réparation mise en pause. Créez un nouveau devis pour l'accord complémentaire.", "warning")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/terminer", methods=["POST"])
@login_required
def terminer(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        terminer_dossier(dossier)
        db.session.commit()
        flash("Dossier terminé. La facture finale devra partir du dernier devis approuvé.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/annuler", methods=["POST"])
@login_required
def annuler(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        annuler_dossier(dossier, request.form.get("motif", ""))
        db.session.commit()
        flash("Dossier annulé.", "warning")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/annuler-facturable", methods=["POST"])
@login_required
def annuler_facturable(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        annuler_dossier_facturable(dossier, request.form.get("motif", ""))
        db.session.commit()
        flash("Dossier annulÃ© avec facturation des travaux effectuÃ©s.", "warning")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/garantie/reouvrir", methods=["POST"])
@login_required
def reouvrir_garantie(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        rouvrir_garantie(dossier, request.form.get("motif", ""))
        db.session.commit()
        flash("Reprise garantie ouverte sur le mÃªme dossier.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


def _obtenir_dossier(dossier_id: int):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier atelier introuvable.", "warning")
    return dossier


def _reponse_devis_pdf(devis_id: int, *, telechargement: bool):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    filename = nom_fichier_devis_pdf(devis)
    disposition = "attachment" if telechargement else "inline"
    return Response(
        exporter_devis_pdf(devis),
        mimetype=PDF_MIMETYPE,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _lignes_devis_depuis_formulaire(dossier: DossierReparation) -> list[dict]:
    designations = request.form.getlist("designation")
    if designations:
        quantites = request.form.getlist("quantite")
        prix = request.form.getlist("prix_unitaire_ht")
        etats = request.form.getlist("etat_piece")
        lignes = []
        for index, designation in enumerate(designations):
            etat_piece = "neuf" if dossier.client.type == "sntl" else (etats[index] if index < len(etats) else "neuf")
            lignes.append(
                {
                    "designation": designation,
                    "quantite": quantites[index] if index < len(quantites) else "1",
                    "prix_unitaire_ht": prix[index] if index < len(prix) else "0",
                    "etat_piece": etat_piece,
                }
            )
        return lignes

    lignes = []
    for index in range(1, 6):
        lignes.append(
            {
                "designation": request.form.get(f"designation_{index}", ""),
                "quantite": request.form.get(f"quantite_{index}", "1"),
                "prix_unitaire_ht": request.form.get(f"prix_unitaire_ht_{index}", "0"),
                "etat_piece": "neuf",
            }
        )
    return lignes


def _obtenir_ou_creer_client() -> Client:
    mode_client = request.form.get("mode_client", "nouveau")
    if mode_client == "existant":
        client_id = request.form.get("client_id")
        client = db.session.get(Client, int(client_id)) if client_id else None
        if not client:
            raise RegleMetierErreur("Sélectionnez un client existant.")
        return client

    type_client = request.form.get("client_type", "particulier")
    if type_client == "sntl":
        preset_key = request.form.get("client_sntl_preset", "").strip()
        if preset_key and preset_key != "custom":
            preset = SNTL_CLIENTS_PREDEFINIS.get(preset_key)
            if not preset:
                raise RegleMetierErreur("Code SNTL predefini invalide.")

            client_existant = Client.query.filter_by(code=preset["code"]).first()
            if client_existant:
                ice = request.form.get("client_ice", "").strip()
                if ice and not client_existant.ice:
                    client_existant.ice = ice
                return client_existant

            client = Client(
                code=preset["code"],
                type="sntl",
                nom=preset["nom"],
                sigle=preset["nom"].upper(),
                telephone=_telephone_ou_erreur(request.form.get("client_telephone")),
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

    nom = request.form.get("client_nom", "").strip()
    if not nom:
        raise RegleMetierErreur("Le nom du client est obligatoire pour ouvrir le dossier.")

    code = request.form.get("client_code", "").strip() or _generer_code_client()
    if Client.query.filter_by(code=code).first():
        raise RegleMetierErreur("Ce code client existe déjà.")

    client = Client(
        code=code,
        type=type_client,
        nom=nom,
        sigle=request.form.get("client_sigle", "").strip(),
        telephone=_telephone_ou_erreur(request.form.get("client_telephone")),
        telephone_2=_telephone_ou_erreur(request.form.get("client_telephone_2")),
        email=request.form.get("client_email", "").strip(),
        adresse=request.form.get("client_adresse", "").strip(),
        ville=request.form.get("client_ville", "").strip(),
        ice=request.form.get("client_ice", "").strip(),
        if_fiscal=request.form.get("client_if_fiscal", "").strip(),
        rc=request.form.get("client_rc", "").strip(),
        administration_rattachee=request.form.get("client_administration_rattachee", "").strip(),
        delai_paiement_jours=_int_ou_none(request.form.get("client_delai_paiement_jours")) or 30,
    )
    db.session.add(client)
    return client


def _obtenir_ou_creer_vehicule(client: Client) -> Vehicule:
    mode_vehicule = request.form.get("mode_vehicule", "nouveau")
    if mode_vehicule == "existant":
        vehicule_id = request.form.get("vehicule_id")
        vehicule = db.session.get(Vehicule, int(vehicule_id)) if vehicule_id else None
        if not vehicule or vehicule.client_id != client.id:
            raise RegleMetierErreur("Sélectionnez un véhicule cohérent avec le client.")
        return vehicule

    immatriculation = request.form.get("vehicule_immatriculation", "").strip()
    marque = request.form.get("vehicule_marque", "").strip()
    modele = request.form.get("vehicule_modele", "").strip()
    if not (immatriculation and marque and modele):
        raise RegleMetierErreur("Immatriculation, marque et modèle sont obligatoires pour ouvrir le dossier.")

    type_immatriculation = "administrative" if client.type == "sntl" else (request.form.get("vehicule_type_immatriculation") or "standard")

    vehicule = Vehicule(
        client_id=client.id,
        immatriculation=immatriculation,
        marque=marque,
        modele=modele,
        type_immatriculation=type_immatriculation,
        type_vehicule=request.form.get("vehicule_type") or "voiture",
        type_carburant=request.form.get("vehicule_carburant") or None,
        kilometrage_actuel=_int_ou_none(request.form.get("kilometrage_entree")),
    )
    db.session.add(vehicule)
    return vehicule


def _generer_code_client() -> str:
    dernier_id = db.session.query(db.func.max(Client.id)).scalar() or 0
    return f"C{dernier_id + 1:04d}"


def _telephone_ou_erreur(valeur: str | None) -> str:
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

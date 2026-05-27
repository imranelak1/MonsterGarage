from datetime import date

from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Client, DevisReparation, DocumentDossier, DossierReparation, PieceDossier, Utilisateur, Vehicule
from app.services.documents import CATEGORIES_DOCUMENTS, chemin_document, enregistrer_document
from app.services.dossiers import (
    RegleMetierErreur,
    ajouter_piece,
    annuler_dossier_facturable,
    annuler_dossier,
    approuver_devis,
    changer_statut_piece,
    creer_devis,
    normaliser_numero_bon_sntl,
    normaliser_priorite,
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

STATUTS_PIECES = ["a_commander", "commandee", "recue", "annulee"]


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


@bp.route("/devis")
@login_required
def liste_devis():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    requete = (
        DevisReparation.query
        .join(DevisReparation.dossier)
        .join(DossierReparation.client)
        .join(DossierReparation.vehicule)
    )
    if statut:
        requete = requete.filter(DevisReparation.statut == statut)
    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            db.or_(
                DevisReparation.objet.ilike(motif),
                DossierReparation.numero.ilike(motif),
                Client.nom.ilike(motif),
                Client.code.ilike(motif),
                Vehicule.immatriculation.ilike(motif),
                Vehicule.marque.ilike(motif),
                Vehicule.modele.ilike(motif),
            )
        )
    devis = requete.order_by(DevisReparation.created_at.desc()).limit(100).all()
    return render_template("dossiers/devis_liste.html", devis=devis, statut=statut, recherche=recherche)


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    clients = Client.query.order_by(Client.nom.asc()).all()
    vehicules = Vehicule.query.order_by(Vehicule.immatriculation.asc()).all()
    utilisateurs = Utilisateur.query.filter_by(actif=True).order_by(Utilisateur.nom_complet.asc()).all()

    def afficher_formulaire():
        return render_template(
            "dossiers/formulaire.html",
            clients=clients,
            vehicules=vehicules,
            utilisateurs=utilisateurs,
            sntl_presets=SNTL_CLIENTS_PREDEFINIS,
            form_data=request.form,
        )

    if request.method == "POST":
        demande_client = request.form.get("demande_client", "").strip()
        if not demande_client:
            flash("La demande client est obligatoire.", "danger")
            return afficher_formulaire()

        try:
            client = _obtenir_ou_creer_client()
            db.session.flush()
            vehicule = _obtenir_ou_creer_vehicule(client)
            db.session.flush()
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return afficher_formulaire()

        try:
            numero_bon_sntl = (
                normaliser_numero_bon_sntl(request.form.get("numero_bon_sntl"))
                if client.type == "sntl"
                else request.form.get("numero_bon_sntl", "").strip()
            )
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return afficher_formulaire()

        dossier = DossierReparation(
            numero=generer_numero_dossier(),
            client_id=client.id,
            vehicule_id=vehicule.id,
            created_by_id=current_user.id,
            responsable_id=_responsable_id_ou_defaut(request.form.get("responsable_id")),
            priorite=normaliser_priorite(request.form.get("priorite")),
            date_promesse=_date_ou_none(request.form.get("date_promesse")),
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

    return render_template(
        "dossiers/formulaire.html",
        clients=clients,
        vehicules=vehicules,
        utilisateurs=utilisateurs,
        sntl_presets=SNTL_CLIENTS_PREDEFINIS,
        form_data={},
    )


@bp.route("/<int:dossier_id>")
@login_required
def detail(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))
    return render_template(
        "dossiers/detail.html",
        dossier=dossier,
        categories_documents=sorted(CATEGORIES_DOCUMENTS),
        statuts_pieces=STATUTS_PIECES,
    )


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


@bp.route("/<int:dossier_id>/note", methods=["POST"])
@login_required
def ajouter_note(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    note = request.form.get("note", "").strip()
    if not note:
        flash("La note est vide.", "warning")
        return redirect(url_for("dossiers.detail", dossier_id=dossier.id))

    journaliser(dossier, "note", note)
    db.session.commit()
    flash("Note ajoutée au dossier.", "success")
    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/<int:dossier_id>/documents", methods=["POST"])
@login_required
def ajouter_document(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        enregistrer_document(
            dossier,
            request.files.get("document"),
            categorie=request.form.get("categorie", "autre"),
            description=request.form.get("description", ""),
        )
        db.session.commit()
        flash("Document ajoute au dossier.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/documents/<int:document_id>/telecharger")
@login_required
def telecharger_document(document_id):
    document = db.session.get(DocumentDossier, document_id)
    if not document:
        flash("Document introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        chemin = chemin_document(document)
    except RegleMetierErreur as erreur:
        flash(str(erreur), "danger")
        return redirect(url_for("dossiers.detail", dossier_id=document.dossier_id))

    return send_file(
        chemin,
        mimetype=document.mime_type,
        as_attachment=True,
        download_name=document.nom_original,
    )


@bp.route("/<int:dossier_id>/pieces", methods=["POST"])
@login_required
def ajouter_piece_dossier(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        ajouter_piece(
            dossier,
            designation=request.form.get("designation", ""),
            quantite=request.form.get("quantite", "1"),
            fournisseur=request.form.get("fournisseur", ""),
            prix_achat_ht=request.form.get("prix_achat_ht", ""),
            date_prevue=_date_ou_none(request.form.get("date_prevue")),
            notes=request.form.get("notes", ""),
        )
        db.session.commit()
        flash("Piece ajoutee au suivi.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


@bp.route("/pieces/<int:piece_id>/statut", methods=["POST"])
@login_required
def changer_piece(piece_id):
    piece = db.session.get(PieceDossier, piece_id)
    if not piece:
        flash("Piece introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        changer_statut_piece(piece, request.form.get("statut", ""))
        db.session.commit()
        flash("Statut de piece mis a jour.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=piece.dossier_id))


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

    vehicule_existant = Vehicule.query.filter_by(immatriculation=immatriculation).first()
    if vehicule_existant:
        if vehicule_existant.client_id == client.id:
            return vehicule_existant
        raise RegleMetierErreur("Cette immatriculation existe deja sur un autre client.")

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


def _date_ou_none(valeur: str | None):
    if not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None


def _responsable_id_ou_defaut(valeur: str | None) -> int:
    if valeur:
        try:
            utilisateur = db.session.get(Utilisateur, int(valeur))
        except ValueError:
            utilisateur = None
        if utilisateur and utilisateur.actif:
            return utilisateur.id
    return current_user.id

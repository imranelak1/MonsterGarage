from decimal import Decimal

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Client, DevisReparation, DossierReparation, Vehicule
from app.services.dossiers import (
    RegleMetierErreur,
    annuler_dossier_facturable,
    annuler_dossier,
    approuver_devis,
    creer_devis,
    generer_numero_dossier,
    journaliser,
    mettre_en_pause,
    modifier_devis,
    refuser_devis,
    rouvrir_garantie,
    terminer_dossier,
)
from app.services.dossiers_sntl import est_dossier_sntl
from app.services.date_filters import appliquer_filtre_periode, periode_depuis_requete
from app.services.devis_totaux import calculer_totaux_lignes, montant_ttc_ligne, taux_tva_ligne
from app.services.attestation_immobilisation import (
    DOCX_MIMETYPE,
    exporter_attestation_docx,
    exporter_attestation_pdf,
    nom_fichier_attestation,
)
from app.services.export_documents import XLSX_MIMETYPE, exporter_devis_excel, nom_fichier_devis
from app.services.export_pdf import PDF_MIMETYPE, exporter_devis_pdf, montant_en_lettres, nom_fichier_devis_pdf
from app.services.factures import enregistrer_avance_client
from app.services.pagination import paginer
from app.services.parametres import obtenir_entreprise
from app.services.telephone import normaliser_telephone

bp = Blueprint("dossiers", __name__, url_prefix="/dossiers")

@bp.route("/")
@login_required
def liste():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    periode = periode_depuis_requete()
    requete = DossierReparation.query.join(DossierReparation.client).join(DossierReparation.vehicule)
    requete = requete.filter(Client.type != "sntl")
    if statut:
        requete = requete.filter(DossierReparation.statut == statut)
    requete = appliquer_filtre_periode(requete, DossierReparation.created_at, periode)
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
    requete = requete.options(
        joinedload(DossierReparation.client),
        joinedload(DossierReparation.vehicule),
    )
    pagination = paginer(requete.order_by(DossierReparation.created_at.desc()))
    return render_template("dossiers/liste.html", dossiers=pagination.items, pagination=pagination, statut=statut, recherche=recherche, periode=periode)


@bp.route("/devis")
@login_required
def liste_devis():
    statut = request.args.get("statut", "").strip()
    recherche = request.args.get("q", "").strip()
    periode = periode_depuis_requete()
    requete = (
        DevisReparation.query
        .join(DevisReparation.dossier)
        .join(DossierReparation.client)
        .join(DossierReparation.vehicule)
    )
    if statut:
        requete = requete.filter(DevisReparation.statut == statut)
    requete = appliquer_filtre_periode(requete, DevisReparation.created_at, periode)
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
    requete = requete.options(
        joinedload(DevisReparation.dossier).joinedload(DossierReparation.client),
        joinedload(DevisReparation.dossier).joinedload(DossierReparation.vehicule),
    )
    pagination = paginer(requete.order_by(DevisReparation.created_at.desc()))
    return render_template("dossiers/devis_liste.html", devis=pagination.items, pagination=pagination, statut=statut, recherche=recherche, periode=periode)


@bp.route("/nouveau", methods=["GET", "POST"])
@login_required
def nouveau():
    clients = Client.query.filter(Client.type != "sntl").order_by(Client.nom.asc()).all()
    vehicules = Vehicule.query.join(Vehicule.client).filter(Client.type != "sntl").order_by(Vehicule.immatriculation.asc()).all()

    if request.method == "POST":
        demande_client = request.form.get("demande_client", "").strip()
        if not demande_client:
            flash("La demande client est obligatoire.", "danger")
            return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules)

        try:
            client = _obtenir_ou_creer_client()
            db.session.flush()
            vehicule = _obtenir_ou_creer_vehicule(client)
            db.session.flush()
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")
            return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules)

        dossier = DossierReparation(
            numero=generer_numero_dossier(),
            client_id=client.id,
            vehicule_id=vehicule.id,
            created_by_id=current_user.id,
            demande_client=demande_client,
            diagnostic_initial=request.form.get("diagnostic_initial", "").strip(),
            assurance_nom=request.form.get("assurance_nom", "").strip() if client.type == "particulier" else "",
            numero_bon_sntl=request.form.get("numero_bon_sntl", "").strip(),
            kilometrage_entree=_int_ou_none(request.form.get("kilometrage_entree")),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(dossier)
        db.session.flush()
        journaliser(dossier, "dossier_cree", "Dossier atelier créé par l'équipe.")
        db.session.commit()

        flash("Dossier atelier créé. Prochaine étape : devis initial.", "success")
        return redirect(url_for("dossiers.detail", dossier_id=dossier.id))

    return render_template("dossiers/formulaire.html", clients=clients, vehicules=vehicules)


@bp.route("/<int:dossier_id>")
@login_required
def detail(dossier_id):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier atelier introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))
    if est_dossier_sntl(dossier):
        return redirect(url_for("sntl.detail", dossier_id=dossier.id))
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
                est_complementaire=request.form.get("mode_devis") == "complementaire",
                confirmer_remplacement_complements=bool(request.form.get("confirmer_remplacement_complements")),
            )
            db.session.commit()
            flash("Devis créé et envoyé en attente d'accord.", "success")
            return redirect(url_for("dossiers.detail", dossier_id=dossier.id))
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")

    return render_template("dossiers/devis_formulaire.html", dossier=dossier)


@bp.route("/devis/<int:devis_id>/modifier", methods=["GET", "POST"])
@login_required
def modifier(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    if devis.statut != "pending":
        flash("Ce devis est déjà validé ou refusé. Créez une nouvelle version si une correction est nécessaire.", "warning")
        endpoint = "sntl.detail" if est_dossier_sntl(devis.dossier) else "dossiers.detail"
        return redirect(url_for(endpoint, dossier_id=devis.dossier_id))

    if request.method == "POST":
        try:
            modifier_devis(
                devis,
                objet=request.form.get("objet", ""),
                lignes_formulaire=_lignes_devis_depuis_formulaire(devis.dossier),
                notes=request.form.get("notes", ""),
            )
            db.session.commit()
            flash("Devis modifié.", "success")
            endpoint = "sntl.detail" if est_dossier_sntl(devis.dossier) else "dossiers.detail"
            return redirect(url_for(endpoint, dossier_id=devis.dossier_id))
        except RegleMetierErreur as erreur:
            db.session.rollback()
            flash(str(erreur), "danger")

    return render_template("dossiers/devis_formulaire.html", dossier=devis.dossier, devis_a_modifier=devis)


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
        est_complementaire = devis.est_complementaire
        refuser_devis(devis, motif=request.form.get("motif_refus", ""))
        db.session.commit()
        if est_complementaire and devis.dossier.statut == "in_progress":
            flash("Complémentaire refusé. Le dossier reprend les travaux déjà approuvés.", "warning")
        else:
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


@bp.route("/devis/<int:devis_id>/impression")
@login_required
def imprimer_devis(devis_id):
    devis = db.session.get(DevisReparation, devis_id)
    if not devis:
        flash("Devis introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    return render_template("dossiers/devis_impression.html", **_contexte_devis_impression(devis))


@bp.route("/devis/<int:devis_id>/pdf")
@login_required
def voir_devis_pdf(devis_id):
    return _reponse_devis_pdf(devis_id, telechargement=False)


@bp.route("/devis/<int:devis_id>/pdf/telecharger")
@login_required
def telecharger_devis_pdf(devis_id):
    return _reponse_devis_pdf(devis_id, telechargement=True)


@bp.route("/<int:dossier_id>/attestation-immobilisation/pdf")
@login_required
def attestation_immobilisation_pdf(dossier_id):
    return _reponse_attestation_immobilisation(dossier_id, "pdf")


@bp.route("/<int:dossier_id>/attestation-immobilisation/docx")
@login_required
def attestation_immobilisation_docx(dossier_id):
    return _reponse_attestation_immobilisation(dossier_id, "docx")


@bp.route("/<int:dossier_id>/pause", methods=["POST"])
@login_required
def pause(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        mettre_en_pause(dossier, request.form.get("raison", ""))
        db.session.commit()
        flash("Réparation mise en pause. Modifiez le devis ou créez un complémentaire pour l'accord client.", "warning")
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


@bp.route("/<int:dossier_id>/avances/nouvelle", methods=["POST"])
@login_required
def nouvelle_avance_client(dossier_id):
    dossier = _obtenir_dossier(dossier_id)
    if not dossier:
        return redirect(url_for("dossiers.liste"))

    try:
        enregistrer_avance_client(
            dossier,
            date_valeur=request.form.get("date", ""),
            montant=request.form.get("montant", ""),
            mode_reglement=request.form.get("mode_reglement", "especes"),
            reference=request.form.get("reference", ""),
            notes=request.form.get("notes", ""),
        )
        db.session.commit()
        flash("Avance client enregistrée.", "success")
    except RegleMetierErreur as erreur:
        db.session.rollback()
        flash(str(erreur), "danger")

    return redirect(url_for("dossiers.detail", dossier_id=dossier.id))


def _obtenir_dossier(dossier_id: int):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier atelier introuvable.", "warning")
        return None
    if est_dossier_sntl(dossier):
        flash("Ce dossier appartient au module SNTL.", "warning")
        return None
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


def _contexte_devis_impression(devis: DevisReparation) -> dict:
    lignes = list(devis.lignes)
    type_client = devis.dossier.client.type
    montant_ht, montant_tva, montant_ttc = calculer_totaux_lignes(lignes, type_client)
    lignes_affichees = [
        {
            "designation": (ligne.designation or "").upper(),
            "quantite": _format_nombre(ligne.quantite),
            "etat": _etat_devis_impression(ligne),
            "prix_unitaire_ht": _format_montant(ligne.prix_unitaire_ht),
            "total_ht": _format_montant(ligne.total_ht),
            "tva": f"{int((taux_tva_ligne(ligne, type_client) * 100).quantize(Decimal('1')))}%",
            "total_ttc": _format_montant(montant_ttc_ligne(ligne, type_client)),
        }
        for ligne in lignes
    ]
    return {
        "devis": devis,
        "dossier": devis.dossier,
        "client": devis.dossier.client,
        "vehicule": devis.dossier.vehicule,
        "entreprise": obtenir_entreprise(),
        "lignes": lignes_affichees,
        "lignes_vides": range(max(0, 10 - len(lignes_affichees))),
        "show_etat": type_client != "sntl",
        "numero_devis": f"{devis.dossier.numero}-V{devis.version}",
        "montant_ht": _format_montant(montant_ht),
        "montant_tva": _format_montant(montant_tva),
        "montant_ttc": _format_montant(montant_ttc),
        "montant_ttc_lettres": montant_en_lettres(montant_ttc),
        "logo_url": url_for("static", filename="img/logo_monster_garage.png"),
        "footer_adresse": "Quartier industriel, sidi ghanem N 534 Bis 2, Marrakech",
    }


def _etat_devis_impression(ligne) -> str:
    if getattr(ligne, "type_ligne", None) == "main_oeuvre" or getattr(ligne, "etat_piece", None) == "mo":
        return "MO"
    if getattr(ligne, "etat_piece", None) == "occasion":
        return "OCC"
    if getattr(ligne, "etat_piece", None) == "autre":
        return (getattr(ligne, "etat_piece_autre", "") or "AUTRE").upper()
    return "NEUF"


def _format_montant(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def _format_nombre(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01")).normalize()
    return f"{amount:f}"


def _reponse_attestation_immobilisation(dossier_id: int, extension: str):
    dossier = db.session.get(DossierReparation, dossier_id)
    if not dossier:
        flash("Dossier introuvable.", "warning")
        return redirect(url_for("dossiers.liste"))

    try:
        jours_reparation = _jours_reparation_attestation()
        if extension == "docx":
            data = exporter_attestation_docx(dossier, jours_reparation=jours_reparation)
            mimetype = DOCX_MIMETYPE
        else:
            data = exporter_attestation_pdf(dossier, jours_reparation=jours_reparation)
            mimetype = PDF_MIMETYPE
    except RegleMetierErreur as erreur:
        flash(str(erreur), "danger")
        endpoint = "sntl.detail" if est_dossier_sntl(dossier) else "dossiers.detail"
        return redirect(url_for(endpoint, dossier_id=dossier.id))

    filename = nom_fichier_attestation(dossier, extension)
    return Response(
        data,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _jours_reparation_attestation() -> int:
    valeur = (request.args.get("jours_reparation") or "7").strip()
    try:
        jours = int(valeur)
    except ValueError:
        raise RegleMetierErreur("Le nombre de jours de réparation doit être un nombre entier.") from None
    if jours < 1 or jours > 365:
        raise RegleMetierErreur("Le nombre de jours de réparation doit être compris entre 1 et 365.")
    return jours


def _lignes_devis_depuis_formulaire(dossier: DossierReparation) -> list[dict]:
    designations = request.form.getlist("designation")
    if designations:
        quantites = request.form.getlist("quantite")
        prix = request.form.getlist("prix_unitaire_ht")
        etats = request.form.getlist("etat_piece")
        types_ligne = request.form.getlist("type_ligne")
        etats_autres = request.form.getlist("etat_piece_autre")
        types_mo = request.form.getlist("type_mo")
        lignes = []
        for index, designation in enumerate(designations):
            etat_piece = etats[index] if index < len(etats) else "neuf"
            type_ligne = types_ligne[index] if index < len(types_ligne) else "piece"
            if dossier.client.type == "sntl" and type_ligne != "main_oeuvre":
                etat_piece = "neuf"
            lignes.append(
                {
                    "designation": designation,
                    "quantite": quantites[index] if index < len(quantites) else "1",
                    "prix_unitaire_ht": prix[index] if index < len(prix) else "0",
                    "type_ligne": type_ligne,
                    "etat_piece": etat_piece,
                    "etat_piece_autre": etats_autres[index] if index < len(etats_autres) else "",
                    "type_mo": types_mo[index] if index < len(types_mo) else "",
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
                "type_ligne": request.form.get(f"type_ligne_{index}", "piece"),
                "etat_piece": "neuf",
                "etat_piece_autre": "",
                "type_mo": request.form.get(f"type_mo_{index}", ""),
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
        if client.type == "sntl":
            raise RegleMetierErreur("Utilisez le module SNTL pour creer un dossier SNTL.")
        return client

    type_client = request.form.get("client_type", "particulier")
    if type_client == "sntl":
        raise RegleMetierErreur("Utilisez le module SNTL pour creer un dossier SNTL.")

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

    vehicule = Vehicule(
        client_id=client.id,
        immatriculation=immatriculation,
        marque=marque,
        modele=modele,
        type_immatriculation=request.form.get("vehicule_type_immatriculation") or "standard",
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

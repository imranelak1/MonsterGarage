from datetime import date
from decimal import Decimal, InvalidOperation
import re

from flask_login import current_user

from app.extensions import db
from app.models import DevisReparation, DossierReparation, JournalAction, LigneDevisReparation
from app.services.devis_totaux import calculer_totaux_lignes
from app.services.workflow import transition_dossier_autorisee

MODES_ACCORD_AUTORISES = {"telephone", "signature", "presentiel", "systeme"}
TYPES_LIGNE_AUTORISES = {"piece", "main_oeuvre", "autre"}
ETATS_LIGNE_AUTORISES = {"neuf", "occasion", "mo", "autre"}
TYPES_MO_AUTORISES = {"mecanique", "electricite", "tolerie", "peinture", "diagnostic", "autre"}


class RegleMetierErreur(ValueError):
    pass


def generer_numero_dossier() -> str:
    dernier_id = db.session.query(db.func.max(DossierReparation.id)).scalar() or 0
    return f"DA-{dernier_id + 1:05d}"


def generer_numero_bon_sntl() -> str:
    prefix = date.today().strftime("%y%m%d")
    numeros = (
        db.session.query(DossierReparation.numero_bon_sntl)
        .filter(DossierReparation.numero_bon_sntl.like(f"{prefix}%"))
        .all()
    )
    suffixes = [
        int(numero[0][6:])
        for numero in numeros
        if numero[0] and re.fullmatch(rf"{prefix}\d{{6}}", numero[0])
    ]
    return f"{prefix}{max(suffixes, default=0) + 1:06d}"


def normaliser_numero_bon_sntl(valeur: str | None) -> str:
    chiffres = re.sub(r"\D", "", valeur or "")
    if not chiffres:
        return generer_numero_bon_sntl()
    if len(chiffres) != 12:
        raise RegleMetierErreur("Le numero de bon SNTL doit contenir 12 chiffres.")
    return chiffres


def journaliser(dossier: DossierReparation, action: str, details: str = "") -> None:
    db.session.add(
        JournalAction(
            dossier_id=dossier.id,
            utilisateur_id=current_user.id,
            action=action,
            details=details,
        )
    )


def changer_statut_dossier(dossier: DossierReparation, nouveau_statut: str) -> None:
    if not transition_dossier_autorisee(dossier.statut, nouveau_statut):
        raise RegleMetierErreur(f"Transition dossier invalide: {dossier.statut} -> {nouveau_statut}.")
    dossier.statut = nouveau_statut


def creer_devis(
    dossier: DossierReparation,
    objet: str,
    lignes_formulaire: list[dict],
    notes: str = "",
    est_complementaire: bool = False,
    confirmer_remplacement_complements: bool = False,
) -> DevisReparation:
    if any(devis.statut == "pending" for devis in dossier.devis):
        raise RegleMetierErreur("Un devis est déjà en attente d'accord pour ce dossier.")

    if dossier.statut not in {"pending_devis", "paused_pending_approval"}:
        raise RegleMetierErreur("Un devis ne peut être créé que si le dossier attend un devis ou un nouvel accord.")

    if (
        not est_complementaire
        and dossier.devis_complementaires_facturables
        and not confirmer_remplacement_complements
    ):
        raise RegleMetierErreur(
            "Confirmez le remplacement des devis complémentaires approuvés avant de créer une version complète."
        )

    lignes = [_normaliser_ligne(ligne) for ligne in lignes_formulaire if ligne.get("designation", "").strip()]
    if not lignes:
        raise RegleMetierErreur("Ajoutez au moins une ligne au devis.")

    version = (max([devis.version for devis in dossier.devis], default=0) + 1)
    montant_ht, montant_tva, montant_ttc = calculer_totaux_lignes(lignes, dossier.client.type)

    devis = DevisReparation(
        dossier_id=dossier.id,
        version=version,
        objet=objet.strip() or f"Devis version {version}",
        montant_ht=montant_ht,
        montant_tva=montant_tva,
        montant_ttc=montant_ttc,
        est_complementaire=est_complementaire,
        notes=notes.strip(),
        created_by_id=current_user.id,
    )
    db.session.add(devis)
    db.session.flush()

    for ligne in lignes:
        db.session.add(
            LigneDevisReparation(
                devis_id=devis.id,
                designation=ligne["designation"],
                quantite=ligne["quantite"],
                prix_unitaire_ht=ligne["prix_unitaire_ht"],
                total_ht=ligne["total_ht"],
                type_ligne=ligne["type_ligne"],
                etat_piece=ligne["etat_piece"],
                etat_piece_autre=ligne["etat_piece_autre"],
                type_mo=ligne["type_mo"],
            )
        )

    changer_statut_dossier(dossier, "pending_approval")
    journaliser(dossier, "devis_cree", f"Devis v{version} créé pour {montant_ttc} MAD TTC.")
    return devis


def modifier_devis(devis: DevisReparation, objet: str, lignes_formulaire: list[dict], notes: str = "") -> DevisReparation:
    if devis.statut != "pending":
        raise RegleMetierErreur("Seul un devis en attente peut être modifié directement.")

    lignes = [_normaliser_ligne(ligne) for ligne in lignes_formulaire if ligne.get("designation", "").strip()]
    if not lignes:
        raise RegleMetierErreur("Ajoutez au moins une ligne au devis.")

    devis.objet = objet.strip() or devis.objet
    devis.notes = notes.strip()
    devis.montant_ht, devis.montant_tva, devis.montant_ttc = calculer_totaux_lignes(lignes, devis.dossier.client.type)

    devis.lignes[:] = []
    db.session.flush()
    for ligne in lignes:
        devis.lignes.append(
            LigneDevisReparation(
                designation=ligne["designation"],
                quantite=ligne["quantite"],
                prix_unitaire_ht=ligne["prix_unitaire_ht"],
                total_ht=ligne["total_ht"],
                type_ligne=ligne["type_ligne"],
                etat_piece=ligne["etat_piece"],
                etat_piece_autre=ligne["etat_piece_autre"],
                type_mo=ligne["type_mo"],
            )
        )

    journaliser(devis.dossier, "devis_modifie", f"Devis v{devis.version} modifié pour {devis.montant_ttc} MAD TTC.")
    return devis


def approuver_devis(devis: DevisReparation, mode_accord: str, accord_assurance: bool = False) -> None:
    dossier = devis.dossier
    mode_accord = mode_accord if mode_accord in MODES_ACCORD_AUTORISES else "telephone"
    if devis != dossier.dernier_devis:
        raise RegleMetierErreur("Seule la dernière version du devis peut être approuvée.")

    if devis.statut != "pending":
        raise RegleMetierErreur("Ce devis n'est plus en attente d'accord.")

    if dossier.statut not in {"pending_approval", "paused_pending_approval"}:
        raise RegleMetierErreur("Le dossier n'attend pas d'accord client.")

    devis.statut = "approved"
    devis.mode_accord = mode_accord
    devis.accord_client = True
    devis.accord_assurance = accord_assurance
    devis.approuve_par_id = current_user.id
    devis.approuve_le = db.func.now()
    changer_statut_dossier(dossier, "in_progress")
    journaliser(dossier, "devis_approuve", f"Devis v{devis.version} approuvé via {mode_accord}.")


def refuser_devis(devis: DevisReparation, motif: str = "") -> None:
    dossier = devis.dossier
    if devis != dossier.dernier_devis:
        raise RegleMetierErreur("Seule la dernière version du devis peut être refusée.")

    if devis.statut != "pending":
        raise RegleMetierErreur("Ce devis n'est plus en attente.")

    devis.statut = "rejected"
    devis.motif_refus = motif.strip()
    if devis.est_complementaire and _devis_base_approuve_avant(devis):
        changer_statut_dossier(dossier, "in_progress")
        journaliser(
            dossier,
            "devis_complementaire_refuse",
            f"Devis complémentaire v{devis.version} refusé. Reprise des travaux déjà approuvés.",
        )
        return

    changer_statut_dossier(dossier, "pending_devis")
    journaliser(dossier, "devis_refuse", f"Devis v{devis.version} refusé. Créer une version corrigée ou annuler le dossier.")


def mettre_en_pause(dossier: DossierReparation, raison: str) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Seul un dossier en réparation peut être mis en pause.")

    changer_statut_dossier(dossier, "paused_pending_approval")
    journaliser(dossier, "pause_accord_requis", raison.strip() or "Travaux supplémentaires détectés.")


def _devis_base_approuve_avant(devis: DevisReparation) -> bool:
    return any(
        autre.statut == "approved"
        and not autre.est_complementaire
        and autre.version < devis.version
        for autre in devis.dossier.devis
    )


def terminer_dossier(dossier: DossierReparation) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Le dossier doit être en réparation pour être terminé.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Impossible de terminer sans devis approuvé.")

    changer_statut_dossier(dossier, "completed")
    journaliser(dossier, "dossier_termine", "Réparation terminée. Facture à générer depuis le dernier devis approuvé.")


def annuler_dossier(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled_billable"}:
        raise RegleMetierErreur("Un dossier termine ou deja facturable ne peut pas etre annule simplement.")

    changer_statut_dossier(dossier, "cancelled")
    journaliser(dossier, "dossier_annule", motif.strip())


def annuler_dossier_facturable(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled", "cancelled_billable"}:
        raise RegleMetierErreur("Ce dossier ne peut plus etre bascule en annulation facturable.")

    if dossier.facture:
        raise RegleMetierErreur("Une facture existe deja pour ce dossier.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Creez et approuvez un devis limite aux travaux effectues avant de facturer l'annulation.")

    changer_statut_dossier(dossier, "cancelled_billable")
    journaliser(
        dossier,
        "dossier_annule_facturable",
        motif.strip() or "Reparation annulee, facturation limitee aux travaux effectues.",
    )


def rouvrir_garantie(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut != "completed" or not dossier.facture:
        raise RegleMetierErreur("La reprise garantie concerne uniquement un dossier deja facture.")

    changer_statut_dossier(dossier, "in_progress")
    journaliser(
        dossier,
        "reprise_garantie",
        motif.strip() or "Retour client apres facturation finale : reprise sous garantie sur le meme dossier.",
    )


def _normaliser_ligne(ligne: dict) -> dict:
    designation = ligne.get("designation", "").strip()
    quantite = _decimal(ligne.get("quantite"), Decimal("1"))
    prix_unitaire_ht = _decimal(ligne.get("prix_unitaire_ht"), Decimal("0"))
    type_ligne = ligne.get("type_ligne") if ligne.get("type_ligne") in TYPES_LIGNE_AUTORISES else "piece"
    type_mo = ligne.get("type_mo") if ligne.get("type_mo") in TYPES_MO_AUTORISES else None
    etat_piece = ligne.get("etat_piece") if ligne.get("etat_piece") in ETATS_LIGNE_AUTORISES else "neuf"
    etat_piece_autre = (ligne.get("etat_piece_autre") or "").strip()
    if type_ligne == "main_oeuvre":
        etat_piece = "mo"
        type_mo = type_mo or "mecanique"
    elif etat_piece == "mo":
        type_ligne = "main_oeuvre"
        type_mo = type_mo or "mecanique"
    elif etat_piece == "autre" and not etat_piece_autre:
        etat_piece_autre = "Autre"
    total_ht = (quantite * prix_unitaire_ht).quantize(Decimal("0.01"))
    return {
        "designation": designation,
        "quantite": quantite,
        "prix_unitaire_ht": prix_unitaire_ht,
        "type_ligne": type_ligne,
        "etat_piece": etat_piece,
        "etat_piece_autre": etat_piece_autre,
        "type_mo": type_mo,
        "total_ht": total_ht,
    }


def _decimal(valeur, defaut: Decimal) -> Decimal:
    try:
        return Decimal(str(valeur or defaut)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return defaut

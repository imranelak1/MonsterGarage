from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import DevisReparation, DossierReparation, JournalAction, LigneDevisReparation, PieceDossier

TAUX_TVA_DEFAUT = Decimal("0.20")
MODES_ACCORD_AUTORISES = {"telephone", "signature", "presentiel", "systeme"}
PRIORITES_AUTORISEES = {"basse", "normale", "haute", "urgente"}
STATUTS_PIECES_AUTORISES = {"a_commander", "commandee", "recue", "annulee"}


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


def normaliser_priorite(valeur: str | None) -> str:
    return valeur if valeur in PRIORITES_AUTORISEES else "normale"


def journaliser(
    dossier: DossierReparation,
    action: str,
    details: str = "",
    *,
    objet_type: str | None = None,
    objet_id: int | None = None,
    ancien_statut: str | None = None,
    nouveau_statut: str | None = None,
    metadonnees: dict | None = None,
) -> None:
    db.session.add(
        JournalAction(
            dossier_id=dossier.id,
            utilisateur_id=current_user.id,
            action=action,
            details=details,
            objet_type=objet_type,
            objet_id=objet_id,
            ancien_statut=ancien_statut,
            nouveau_statut=nouveau_statut,
            metadonnees=json.dumps(metadonnees, ensure_ascii=True) if metadonnees else None,
            ip_adresse=request.remote_addr if has_request_context() else None,
        )
    )


def changer_statut(dossier: DossierReparation, nouveau_statut: str, action: str, details: str = "") -> None:
    ancien_statut = dossier.statut
    dossier.statut = nouveau_statut
    journaliser(
        dossier,
        action,
        details,
        ancien_statut=ancien_statut,
        nouveau_statut=nouveau_statut,
    )


def creer_devis(dossier: DossierReparation, objet: str, lignes_formulaire: list[dict], notes: str = "") -> DevisReparation:
    if any(devis.statut == "pending" for devis in dossier.devis):
        raise RegleMetierErreur("Un devis est deja en attente d'accord pour ce dossier.")

    if dossier.statut not in {"pending_devis", "paused_pending_approval"}:
        raise RegleMetierErreur("Un devis ne peut etre cree que si le dossier attend un devis ou un accord complementaire.")

    lignes = [_normaliser_ligne(ligne) for ligne in lignes_formulaire if ligne.get("designation", "").strip()]
    if not lignes:
        raise RegleMetierErreur("Ajoutez au moins une ligne au devis.")

    version = max([devis.version for devis in dossier.devis], default=0) + 1
    montant_ht = sum(ligne["total_ht"] for ligne in lignes)
    montant_tva = (montant_ht * TAUX_TVA_DEFAUT).quantize(Decimal("0.01"))
    montant_ttc = (montant_ht + montant_tva).quantize(Decimal("0.01"))

    devis = DevisReparation(
        dossier_id=dossier.id,
        version=version,
        objet=objet.strip() or f"Devis version {version}",
        montant_ht=montant_ht,
        montant_tva=montant_tva,
        montant_ttc=montant_ttc,
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
                etat_piece=ligne["etat_piece"],
            )
        )

    changer_statut(dossier, "pending_approval", "devis_cree", f"Devis v{version} cree pour {montant_ttc} MAD TTC.")
    return devis


def approuver_devis(devis: DevisReparation, mode_accord: str, accord_assurance: bool = False) -> None:
    dossier = devis.dossier
    mode_accord = mode_accord if mode_accord in MODES_ACCORD_AUTORISES else "telephone"
    if devis != dossier.dernier_devis:
        raise RegleMetierErreur("Seule la derniere version du devis peut etre approuvee.")

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
    dossier.motif_blocage = None
    changer_statut(dossier, "in_progress", "devis_approuve", f"Devis v{devis.version} approuve via {mode_accord}.")


def refuser_devis(devis: DevisReparation, motif: str = "") -> None:
    dossier = devis.dossier
    if devis != dossier.dernier_devis:
        raise RegleMetierErreur("Seule la derniere version du devis peut etre refusee.")

    if devis.statut != "pending":
        raise RegleMetierErreur("Ce devis n'est plus en attente.")

    devis.statut = "rejected"
    devis.motif_refus = motif.strip()
    changer_statut(
        dossier,
        "pending_devis",
        "devis_refuse",
        f"Devis v{devis.version} refuse. Creer une version corrigee ou annuler le dossier.",
    )


def mettre_en_pause(dossier: DossierReparation, raison: str) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Seul un dossier en reparation peut etre mis en pause.")

    dossier.motif_blocage = raison.strip() or "Travaux supplementaires detectes."
    changer_statut(dossier, "paused_pending_approval", "pause_accord_requis", dossier.motif_blocage)


def terminer_dossier(dossier: DossierReparation) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Le dossier doit etre en reparation pour etre termine.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Impossible de terminer sans devis approuve.")

    dossier.motif_blocage = None
    changer_statut(
        dossier,
        "completed",
        "dossier_termine",
        "Reparation terminee. Facture a generer depuis le dernier devis approuve.",
    )


def annuler_dossier(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled_billable"}:
        raise RegleMetierErreur("Un dossier termine ou deja facturable ne peut pas etre annule simplement.")

    changer_statut(dossier, "cancelled", "dossier_annule", motif.strip())


def annuler_dossier_facturable(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled", "cancelled_billable"}:
        raise RegleMetierErreur("Ce dossier ne peut plus etre bascule en annulation facturable.")

    if dossier.facture:
        raise RegleMetierErreur("Une facture existe deja pour ce dossier.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Creez et approuvez un devis limite aux travaux effectues avant de facturer l'annulation.")

    changer_statut(
        dossier,
        "cancelled_billable",
        "dossier_annule_facturable",
        motif.strip() or "Reparation annulee, facturation limitee aux travaux effectues.",
    )


def rouvrir_garantie(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut != "completed" or not dossier.facture:
        raise RegleMetierErreur("La reprise garantie concerne uniquement un dossier deja facture.")

    changer_statut(
        dossier,
        "in_progress",
        "reprise_garantie",
        motif.strip() or "Retour client apres facturation finale : reprise sous garantie sur le meme dossier.",
    )


def ajouter_piece(
    dossier: DossierReparation,
    designation: str,
    quantite,
    fournisseur: str = "",
    prix_achat_ht=None,
    date_prevue=None,
    notes: str = "",
) -> PieceDossier:
    designation = designation.strip()
    if not designation:
        raise RegleMetierErreur("La designation de la piece est obligatoire.")

    piece = PieceDossier(
        dossier_id=dossier.id,
        created_by_id=current_user.id,
        designation=designation,
        quantite=_decimal(quantite, Decimal("1")),
        fournisseur=fournisseur.strip(),
        prix_achat_ht=_decimal(prix_achat_ht, Decimal("0")) if prix_achat_ht not in (None, "") else None,
        date_prevue=date_prevue,
        notes=notes.strip(),
    )
    db.session.add(piece)
    db.session.flush()
    journaliser(
        dossier,
        "piece_ajoutee",
        f"Piece ajoutee : {piece.designation} x {piece.quantite}.",
        objet_type="piece_dossier",
        objet_id=piece.id,
    )
    return piece


def changer_statut_piece(piece: PieceDossier, statut: str) -> None:
    if statut not in STATUTS_PIECES_AUTORISES:
        raise RegleMetierErreur("Statut de piece invalide.")

    ancien_statut = piece.statut
    piece.statut = statut
    journaliser(
        piece.dossier,
        "piece_statut",
        f"Piece {piece.designation} : {ancien_statut} -> {statut}.",
        objet_type="piece_dossier",
        objet_id=piece.id,
        ancien_statut=ancien_statut,
        nouveau_statut=statut,
    )


def _normaliser_ligne(ligne: dict) -> dict:
    designation = ligne.get("designation", "").strip()
    quantite = _decimal(ligne.get("quantite"), Decimal("1"))
    prix_unitaire_ht = _decimal(ligne.get("prix_unitaire_ht"), Decimal("0"))
    etat_piece = ligne.get("etat_piece") if ligne.get("etat_piece") in {"neuf", "occasion"} else "neuf"
    total_ht = (quantite * prix_unitaire_ht).quantize(Decimal("0.01"))
    return {
        "designation": designation,
        "quantite": quantite,
        "prix_unitaire_ht": prix_unitaire_ht,
        "etat_piece": etat_piece,
        "total_ht": total_ht,
    }


def _decimal(valeur, defaut: Decimal) -> Decimal:
    try:
        return Decimal(str(valeur or defaut)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return defaut

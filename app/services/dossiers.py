from decimal import Decimal, InvalidOperation

from flask_login import current_user

from app.extensions import db
from app.models import DevisReparation, DossierReparation, JournalAction, LigneDevisReparation

TAUX_TVA_DEFAUT = Decimal("0.20")
MODES_ACCORD_AUTORISES = {"telephone", "signature", "presentiel", "systeme"}


class RegleMetierErreur(ValueError):
    pass


def generer_numero_dossier() -> str:
    dernier_id = db.session.query(db.func.max(DossierReparation.id)).scalar() or 0
    return f"DA-{dernier_id + 1:05d}"


def journaliser(dossier: DossierReparation, action: str, details: str = "") -> None:
    db.session.add(
        JournalAction(
            dossier_id=dossier.id,
            utilisateur_id=current_user.id,
            action=action,
            details=details,
        )
    )


def creer_devis(dossier: DossierReparation, objet: str, lignes_formulaire: list[dict], notes: str = "") -> DevisReparation:
    if any(devis.statut == "pending" for devis in dossier.devis):
        raise RegleMetierErreur("Un devis est déjà en attente d'accord pour ce dossier.")

    if dossier.statut not in {"pending_devis", "paused_pending_approval"}:
        raise RegleMetierErreur("Un devis ne peut être créé que si le dossier attend un devis ou un accord complémentaire.")

    lignes = [_normaliser_ligne(ligne) for ligne in lignes_formulaire if ligne.get("designation", "").strip()]
    if not lignes:
        raise RegleMetierErreur("Ajoutez au moins une ligne au devis.")

    version = (max([devis.version for devis in dossier.devis], default=0) + 1)
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

    dossier.statut = "pending_approval"
    journaliser(dossier, "devis_cree", f"Devis v{version} créé pour {montant_ttc} MAD TTC.")
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
    dossier.statut = "in_progress"
    journaliser(dossier, "devis_approuve", f"Devis v{devis.version} approuvé via {mode_accord}.")


def refuser_devis(devis: DevisReparation, motif: str = "") -> None:
    dossier = devis.dossier
    if devis != dossier.dernier_devis:
        raise RegleMetierErreur("Seule la dernière version du devis peut être refusée.")

    if devis.statut != "pending":
        raise RegleMetierErreur("Ce devis n'est plus en attente.")

    devis.statut = "rejected"
    devis.motif_refus = motif.strip()
    dossier.statut = "pending_devis"
    journaliser(dossier, "devis_refuse", f"Devis v{devis.version} refusé. Créer une version corrigée ou annuler le dossier.")


def mettre_en_pause(dossier: DossierReparation, raison: str) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Seul un dossier en réparation peut être mis en pause.")

    dossier.statut = "paused_pending_approval"
    journaliser(dossier, "pause_accord_requis", raison.strip() or "Travaux supplémentaires détectés.")


def terminer_dossier(dossier: DossierReparation) -> None:
    if dossier.statut != "in_progress":
        raise RegleMetierErreur("Le dossier doit être en réparation pour être terminé.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Impossible de terminer sans devis approuvé.")

    dossier.statut = "completed"
    journaliser(dossier, "dossier_termine", "Réparation terminée. Facture à générer depuis le dernier devis approuvé.")


def annuler_dossier(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled_billable"}:
        raise RegleMetierErreur("Un dossier termine ou deja facturable ne peut pas etre annule simplement.")

    dossier.statut = "cancelled"
    journaliser(dossier, "dossier_annule", motif.strip())


def annuler_dossier_facturable(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut in {"completed", "cancelled", "cancelled_billable"}:
        raise RegleMetierErreur("Ce dossier ne peut plus etre bascule en annulation facturable.")

    if dossier.facture:
        raise RegleMetierErreur("Une facture existe deja pour ce dossier.")

    if not dossier.dernier_devis_approuve:
        raise RegleMetierErreur("Creez et approuvez un devis limite aux travaux effectues avant de facturer l'annulation.")

    dossier.statut = "cancelled_billable"
    journaliser(
        dossier,
        "dossier_annule_facturable",
        motif.strip() or "Reparation annulee, facturation limitee aux travaux effectues.",
    )


def rouvrir_garantie(dossier: DossierReparation, motif: str) -> None:
    if dossier.statut != "completed" or not dossier.facture:
        raise RegleMetierErreur("La reprise garantie concerne uniquement un dossier deja facture.")

    dossier.statut = "in_progress"
    journaliser(
        dossier,
        "reprise_garantie",
        motif.strip() or "Retour client apres facturation finale : reprise sous garantie sur le meme dossier.",
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

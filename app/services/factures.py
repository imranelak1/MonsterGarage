from decimal import Decimal, InvalidOperation

from flask_login import current_user

from app.extensions import db
from app.models import DossierReparation, FactureReparation
from app.services.dossiers import RegleMetierErreur, journaliser


def generer_numero_facture() -> str:
    dernier_id = db.session.query(db.func.max(FactureReparation.id)).scalar() or 0
    return f"FA-{dernier_id + 1:05d}"


def generer_facture(dossier: DossierReparation) -> FactureReparation:
    if dossier.statut != "completed":
        raise RegleMetierErreur("La facture finale ne peut etre generee qu'apres la fin de la reparation.")

    if dossier.facture:
        raise RegleMetierErreur("Une facture existe deja pour ce dossier.")

    devis = dossier.dernier_devis_approuve
    if not devis:
        raise RegleMetierErreur("Impossible de facturer sans devis approuve.")

    facture = FactureReparation(
        numero=generer_numero_facture(),
        dossier_id=dossier.id,
        devis_id=devis.id,
        montant_ht=devis.montant_ht,
        montant_tva=devis.montant_tva,
        montant_ttc=devis.montant_ttc,
        created_by_id=current_user.id,
    )
    db.session.add(facture)
    db.session.flush()
    journaliser(dossier, "facture_emise", f"Facture {facture.numero} generee depuis le devis v{devis.version}.")
    return facture


def marquer_livree(facture: FactureReparation) -> None:
    if facture.statut != "emise":
        raise RegleMetierErreur("Seule une facture emise peut etre marquee livree.")

    facture.statut = "livree"
    facture.livree_le = db.func.now()
    journaliser(facture.dossier, "vehicule_livre", f"Livraison enregistree pour la facture {facture.numero}.")


def enregistrer_reglement(facture: FactureReparation, mode_reglement: str, montant, reference: str = "") -> None:
    if facture.statut == "reglee":
        raise RegleMetierErreur("Cette facture est deja totalement reglee.")

    if facture.statut != "livree":
        raise RegleMetierErreur("Le reglement s'enregistre apres la livraison du vehicule.")

    if mode_reglement not in {"especes", "cheque", "virement", "carte", "autre"}:
        raise RegleMetierErreur("Mode de reglement invalide.")

    montant_reglement = _decimal_positif(montant)
    reste = Decimal(str(facture.montant_restant)).quantize(Decimal("0.01"))
    if montant_reglement > reste:
        raise RegleMetierErreur(f"Le montant saisi depasse le reste a payer ({reste} MAD).")

    facture.montant_regle = (Decimal(str(facture.montant_regle or 0)) + montant_reglement).quantize(Decimal("0.01"))
    facture.mode_reglement = mode_reglement
    facture.reference_reglement = reference.strip()

    if facture.montant_regle >= facture.montant_ttc:
        facture.statut = "reglee"
        facture.reglee_le = db.func.now()
        action = "facture_reglee"
        details = f"Solde complet de {montant_reglement} MAD enregistre pour la facture {facture.numero} par {facture.mode_reglement_libelle}."
    else:
        facture.statut = "livree"
        facture.reglee_le = None
        action = "paiement_partiel"
        details = (
            f"Paiement partiel de {montant_reglement} MAD enregistre pour la facture {facture.numero}. "
            f"Reste a payer : {facture.montant_restant} MAD."
        )

    journaliser(facture.dossier, action, details)


def _decimal_positif(valeur) -> Decimal:
    try:
        montant = Decimal(str(valeur or "").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise RegleMetierErreur("Saisissez un montant de reglement valide.") from None

    if montant <= 0:
        raise RegleMetierErreur("Le montant du reglement doit etre superieur a 0.")
    return montant

from datetime import date
from decimal import Decimal, InvalidOperation

from flask_login import current_user

from app.extensions import db
from app.models import AvanceClient, DossierReparation, FactureReparation
from app.services.dossiers import RegleMetierErreur, journaliser, normaliser_numero_bon_sntl


def generer_numero_facture() -> str:
    dernier_id = db.session.query(db.func.max(FactureReparation.id)).scalar() or 0
    return f"FA-{dernier_id + 1:05d}"


def generer_facture(dossier: DossierReparation) -> FactureReparation:
    if not dossier.est_facturable:
        raise RegleMetierErreur("La facture ne peut etre generee qu'apres la fin de la reparation ou une annulation facturable.")

    if dossier.facture:
        raise RegleMetierErreur("Une facture existe deja pour ce dossier.")

    devis_facturables = dossier.devis_approuves_facturables
    if not devis_facturables:
        raise RegleMetierErreur("Impossible de facturer sans devis approuve.")

    if dossier.client.type == "sntl" and not dossier.numero_bon_sntl:
        dossier.numero_bon_sntl = normaliser_numero_bon_sntl(None)

    devis_reference = devis_facturables[-1]
    montant_ht = sum((Decimal(str(devis.montant_ht or 0)) for devis in devis_facturables), Decimal("0.00")).quantize(Decimal("0.01"))
    montant_tva = sum((Decimal(str(devis.montant_tva or 0)) for devis in devis_facturables), Decimal("0.00")).quantize(Decimal("0.01"))
    montant_ttc = sum((Decimal(str(devis.montant_ttc or 0)) for devis in devis_facturables), Decimal("0.00")).quantize(Decimal("0.01"))
    montant_avances = min(dossier.montant_avances_client, montant_ttc)

    facture = FactureReparation(
        numero=generer_numero_facture(),
        dossier_id=dossier.id,
        devis_id=devis_reference.id,
        montant_ht=montant_ht,
        montant_tva=montant_tva,
        montant_ttc=montant_ttc,
        montant_regle=montant_avances,
        created_by_id=current_user.id,
    )
    db.session.add(facture)
    db.session.flush()
    if dossier.statut == "cancelled_billable":
        journaliser(dossier, "facture_travaux_effectues", f"Facture {facture.numero} generee pour les travaux effectues depuis {len(devis_facturables)} devis approuve(s).")
    else:
        details = f"Facture {facture.numero} generee depuis {len(devis_facturables)} devis approuve(s)."
        if montant_avances:
            details += f" Avances deduites : {montant_avances} MAD."
        journaliser(dossier, "facture_emise", details)
    return facture


def enregistrer_avance_client(dossier: DossierReparation, date_valeur: str, montant, mode_reglement: str, reference: str = "", notes: str = "") -> AvanceClient:
    if dossier.facture:
        raise RegleMetierErreur("Les avances se saisissent avant la génération de la facture.")

    try:
        date_avance = date.fromisoformat((date_valeur or "").strip())
    except ValueError:
        raise RegleMetierErreur("Date d'avance invalide.") from None

    if mode_reglement not in {"especes", "cheque", "virement", "carte", "autre"}:
        raise RegleMetierErreur("Mode de règlement invalide.")

    avance = AvanceClient(
        dossier_id=dossier.id,
        date=date_avance,
        montant=_decimal_positif(montant),
        mode_reglement=mode_reglement,
        reference=reference.strip(),
        notes=notes.strip(),
        created_by_id=current_user.id,
    )
    db.session.add(avance)
    journaliser(dossier, "avance_client", f"Avance client de {avance.montant} MAD enregistrée.")
    return avance


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
            f"Reste à payer : {facture.montant_restant} MAD."
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

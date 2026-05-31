from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.models import ParametreSysteme


@dataclass(frozen=True)
class CommissionSntl:
    taux_commission: Decimal
    taux_tva: Decimal
    montant_ht: Decimal
    montant_ttc: Decimal
    commission_ht: Decimal
    tva_commission: Decimal
    deduction_totale: Decimal
    net_a_regler: Decimal


def param_percent(cle: str, default: Decimal) -> Decimal:
    param = ParametreSysteme.query.filter_by(cle=cle).first()
    raw = param.valeur if param else default
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        value = default
    return (value / Decimal("100")).quantize(Decimal("0.0001"))


def money_decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def calculer_commission_sntl(montant_ht, montant_ttc=None) -> CommissionSntl:
    taux_tva = param_percent("taux_tva", Decimal("20"))
    taux_commission = param_percent("taux_commission_sntl", Decimal("10"))
    montant_ht = money_decimal(montant_ht)
    if montant_ttc is None:
        montant_ttc = montant_ht + (montant_ht * taux_tva).quantize(Decimal("0.01"))
    montant_ttc = money_decimal(montant_ttc)
    commission_ht = (montant_ht * taux_commission).quantize(Decimal("0.01"))
    tva_commission = (commission_ht * taux_tva).quantize(Decimal("0.01"))
    deduction_totale = (commission_ht + tva_commission).quantize(Decimal("0.01"))
    return CommissionSntl(
        taux_commission=taux_commission,
        taux_tva=taux_tva,
        montant_ht=montant_ht,
        montant_ttc=montant_ttc,
        commission_ht=commission_ht,
        tva_commission=tva_commission,
        deduction_totale=deduction_totale,
        net_a_regler=(montant_ttc - deduction_totale).quantize(Decimal("0.01")),
    )

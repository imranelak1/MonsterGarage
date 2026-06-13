from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import textwrap
import zlib

from PIL import Image

from app.models import DevisReparation, FactureReparation
from app.services.calculs_facturation import calculer_commission_sntl, param_percent
from app.services.devis_totaux import calculer_totaux_lignes, montant_ttc_ligne, taux_tva_ligne
from app.services.parametres import obtenir_entreprise


PDF_MIMETYPE = "application/pdf"

_PAGE_WIDTH = 595.28
_PAGE_HEIGHT = 841.89
_MARGIN = 42
_BLACK = (0, 0, 0)
_WHITE = (1, 1, 1)
_YELLOW = (1, 0.84, 0)
_SLATE = (0.08, 0.1, 0.16)
_LIGHT = (0.94, 0.96, 0.98)
_SNTL_X = {2: 42, 3: 137, 4: 277, 5: 352, 6: 427, 7: 487}
_SNTL_W = {2: 95, 3: 140, 4: 75, 5: 75, 6: 60, 7: 66}
_SNTL_RIGHT = _SNTL_X[7] + _SNTL_W[7]
_LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "img" / "logo_monster_garage.png"
_MONSTER_BLUE = (0.23, 0.53, 0.68)
_MUTED = (0.32, 0.32, 0.32)
_SNTL_DESTINATION = "La Société Nationale des Transports et de la Logistique (SNTL)"
_DEVIS_LEFT = 56
_DEVIS_RIGHT = 500
_DEVIS_FOOTER_ADDRESS = "Quartier industriel, sidi ghanem N 534 Bis 2, Marrakech"


def exporter_devis_pdf(devis: DevisReparation) -> bytes:
    return _build_monster_devis_pdf(devis)


def exporter_facture_pdf(facture: FactureReparation) -> bytes:
    if facture.dossier.client.type == "sntl":
        return _build_sntl_document_pdf(
            titre="FACTURE SNTL",
            numero=facture.numero,
            date_document=facture.created_at,
            devis=facture.devis,
            include_commission=True,
            lignes=facture.lignes_facture,
            montant_ht=facture.montant_ht,
            montant_tva=facture.montant_tva,
            montant_ttc=facture.montant_ttc,
        )
    elif facture.dossier.statut == "cancelled_billable":
        titre = "FACTURE TRAVAUX EFFECTUES"
    else:
        titre = "FACTURE"

    return _build_document_pdf(
        titre=titre,
        numero=facture.numero,
        date_document=facture.created_at,
        devis=facture.devis,
        statut=facture.statut_libelle,
        lignes=facture.lignes_facture,
        montant_ht=facture.montant_ht,
        montant_tva=facture.montant_tva,
        montant_ttc=facture.montant_ttc,
        montant_regle=facture.montant_regle,
    )


def nom_fichier_devis_pdf(devis: DevisReparation) -> str:
    return _safe_filename(f"DEVIS_{devis.dossier.numero}_V{devis.version}.pdf")


def nom_fichier_facture_pdf(facture: FactureReparation) -> str:
    prefix = "FACTURE_SNTL" if facture.dossier.client.type == "sntl" else "FACTURE"
    return _safe_filename(f"{prefix}_{facture.numero}.pdf")


def montant_en_lettres(amount) -> str:
    return _capitalize(_amount_to_french(Decimal(str(amount or 0))))


def _build_monster_devis_pdf(devis: DevisReparation) -> bytes:
    pdf = _PdfDocument()
    ctx = _PageContext(pdf)
    is_sntl = devis.dossier.client.type == "sntl"
    _draw_monster_devis_page(ctx, devis, is_sntl=is_sntl)
    return pdf.render()


def _draw_monster_devis_page(ctx: "_PageContext", devis: DevisReparation, *, is_sntl: bool) -> None:
    lignes = list(devis.lignes)
    client_type = devis.dossier.client.type
    montant_ht, montant_tva, montant_ttc = calculer_totaux_lignes(lignes, client_type)

    _draw_monster_devis_header(ctx)
    if is_sntl:
        table_top = _draw_monster_devis_info_sntl(ctx, devis)
        table_columns = [
            ("Désignation", 153),
            ("Qté", 24),
            ("Prix HT", 57),
            ("Prix HT total", 69),
            ("TVA", 39),
            ("Total TTC", 74),
        ]
        table_x = _DEVIS_LEFT
    else:
        table_top = _draw_monster_devis_info_particulier(ctx, devis)
        table_columns = [
            ("Désignation", 159),
            ("Qté", 25),
            ("Etat", 36),
            ("Prix HT", 61),
            ("Prix HT total", 70),
            ("TVA", 39),
            ("Total TTC", 74),
        ]
        table_x = _DEVIS_LEFT

    table_bottom = _draw_monster_devis_table(ctx, devis, table_x, table_top, table_columns, lignes, show_etat=not is_sntl)
    totals_bottom = _draw_monster_devis_totals(ctx, table_x, table_columns, table_bottom - 8, montant_ht, montant_tva, montant_ttc)
    phrase_y = min(totals_bottom - 36, 360 if not is_sntl else 342)
    _draw_monster_devis_legal(ctx, devis, montant_ttc, phrase_y)
    _draw_monster_devis_signature(ctx, y=248 if is_sntl else 262)
    _draw_monster_devis_footer(ctx)


def _draw_monster_devis_header(ctx: "_PageContext") -> None:
    title_x = _DEVIS_LEFT + 5
    title_y = 776
    ctx.text(title_x, title_y, "MONSTER GARAGE", size=24, bold=True, italic=True, color=_MONSTER_BLUE)
    ctx.line(title_x, title_y - 4, title_x + 244, title_y - 4, color=_MONSTER_BLUE, width=0.8)
    ctx.image(_LOGO_PATH, 328, 762, 104, 49)
    ctx.line(_DEVIS_LEFT, 756, _DEVIS_RIGHT, 756, color=(0.50, 0.50, 0.50), width=0.9)


def _draw_monster_devis_info_sntl(ctx: "_PageContext", devis: DevisReparation) -> float:
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    numero = _numero_devis_modele(devis)
    date_doc = _format_date(devis.created_at)

    left_rows = [
        ("Devis n°", numero),
        ("Date", date_doc),
        ("Véhicule", f"{vehicule.marque} {vehicule.modele}".upper()),
        ("Immatriculation", vehicule.immatriculation),
        ("Kilométrage", dossier.kilometrage_entree or vehicule.kilometrage_actuel or ""),
    ]
    right_rows = [
        ("N°client", client.code),
        ("Client", (client.administration_rattachee or client.nom).upper()),
        ("Adresse", client.adresse or client.ville or ""),
    ]
    _draw_monster_rounded_info_box(ctx, _DEVIS_LEFT, 673, 151, 72, left_rows)
    _draw_monster_rounded_info_box(ctx, 262, 673, 161, 72, right_rows)
    return 615


def _draw_monster_devis_info_particulier(ctx: "_PageContext", devis: DevisReparation) -> float:
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    left_rows = [
        ("Devis n°", _numero_devis_modele(devis)),
        ("Date", _format_date(devis.created_at)),
        ("Véhicule", f"{vehicule.marque} {vehicule.modele}".upper()),
        ("Immatriculation", vehicule.immatriculation),
    ]
    right_rows = [
        ("Client", client.nom.upper()),
        ("ICE n°", client.ice or ""),
        ("Adresse", client.adresse or client.ville or ""),
    ]
    _draw_monster_info_lines(ctx, _DEVIS_LEFT + 7, 704, left_rows, label_width=58)
    _draw_monster_info_lines(ctx, 306, 704, right_rows, label_width=56)
    return 618


def _draw_monster_rounded_info_box(ctx: "_PageContext", x: float, y: float, width: float, height: float, rows: list[tuple[str, object]]) -> None:
    ctx.round_rect(x, y, width, height, 8, stroke=(0.25, 0.25, 0.25))
    line_y = y + height - 15
    for label, value in rows:
        ctx.text(x + 7, line_y, f"{label} :", size=5.4, color=_BLACK)
        ctx.text(x + 72, line_y, _display(value), size=5.2, bold=True, color=_BLACK)
        line_y -= 11


def _draw_monster_info_lines(ctx: "_PageContext", x: float, y: float, rows: list[tuple[str, object]], *, label_width: float) -> None:
    line_y = y
    for label, value in rows:
        ctx.text(x, line_y, f"{label}:", size=6.0, color=_BLACK)
        ctx.text(x + label_width, line_y, _display(value), size=5.8, bold=True, color=_BLACK)
        line_y -= 12


def _draw_monster_devis_table(
    ctx: "_PageContext",
    devis: DevisReparation,
    x: float,
    top: float,
    columns: list[tuple[str, float]],
    lignes: list,
    *,
    show_etat: bool,
) -> float:
    row_height = 13
    header_height = 13
    table_width = sum(width for _, width in columns)
    y = top
    col_x = [x]
    for _, width in columns[:-1]:
        col_x.append(col_x[-1] + width)

    for (label, width), cell_x in zip(columns, col_x):
        _draw_monster_cell(ctx, cell_x, y - header_height, width, header_height, label, size=5.8, bold=True, align="center")
    y -= header_height

    rows_count = max(10, len(lignes))
    for index in range(rows_count):
        ligne = lignes[index] if index < len(lignes) else None
        values = _monster_devis_row_values(ligne, devis.dossier.client.type, show_etat=show_etat)
        for (value, align), (_, width), cell_x in zip(values, columns, col_x):
            _draw_monster_cell(ctx, cell_x, y - row_height, width, row_height, value, size=5.6, bold=False, align=align)
        y -= row_height

    ctx.rect(x, y, table_width, header_height + rows_count * row_height, stroke=_BLACK)
    return y


def _monster_devis_row_values(ligne, client_type: str, *, show_etat: bool) -> list[tuple[object, str]]:
    if ligne is None:
        values = ["", "", "", "", "", ""]
        if show_etat:
            values.insert(2, "")
        return [(value, "center") for value in values]

    tva = taux_tva_ligne(ligne, client_type)
    values = [
        (str(ligne.designation or "").upper(), "left"),
        (_number(ligne.quantite), "center"),
        (_money_fr(ligne.prix_unitaire_ht), "right"),
        (_money_fr(ligne.total_ht), "right"),
        (_percent_label(tva), "center"),
        (_money_fr(montant_ttc_ligne(ligne, client_type)), "right"),
    ]
    if show_etat:
        values.insert(2, (_etat_modele(ligne), "center"))
    return values


def _draw_monster_devis_totals(
    ctx: "_PageContext",
    table_x: float,
    columns: list[tuple[str, float]],
    top: float,
    montant_ht,
    montant_tva,
    montant_ttc,
) -> float:
    table_width = sum(width for _, width in columns)
    width = 166
    x = table_x + table_width - width
    row_height = 12
    rows = [("Total HT", montant_ht), ("TVA", montant_tva), ("Total TTC", montant_ttc)]
    y = top
    for label, amount in rows:
        ctx.rect(x, y - row_height, 68, row_height, fill=(0.93, 0.93, 0.93), stroke=_BLACK)
        ctx.rect(x + 68, y - row_height, width - 68, row_height, stroke=_BLACK)
        ctx.text(x + 4, y - 8, label, size=5.5, bold=True)
        amount_text = _money_mad_compact(amount)
        amount_x = x + width - 4 - _estimated_text_width(amount_text, 5.5)
        ctx.text(amount_x, y - 8, amount_text, size=5.5)
        y -= row_height
    return y


def _draw_monster_devis_legal(ctx: "_PageContext", devis: DevisReparation, montant_ttc, y: float) -> None:
    phrase = f"Arrêté le présent devis à la somme de: {montant_en_lettres(montant_ttc)} TTC"
    ctx.text(_DEVIS_LEFT, y, phrase, size=5.8, bold=True, italic=True)
    ctx.line(_DEVIS_LEFT, y - 2, min(_DEVIS_RIGHT - 52, _DEVIS_LEFT + _estimated_text_width(phrase, 5.8, bold=True)), y - 2, width=0.45)
    ctx.text(_DEVIS_LEFT, y - 24, "Devis reçu avant l'exécution des travaux", size=5.6, italic=True)
    if devis.notes:
        note_lines = _wrap(f"Notes: {devis.notes}", 100)[:3]
        note_y = y - 42
        for line in note_lines:
            ctx.text(58, note_y, line, size=5.4)
            note_y -= 8


def _draw_monster_devis_signature(ctx: "_PageContext", *, y: float) -> None:
    ctx.text(286, y, "Date :", size=5.4)
    ctx.text(273, y - 31, "Bon pour accord", size=5.4)
    ctx.text(270, y - 62, "Signature client", size=5.4)


def _draw_monster_devis_footer(ctx: "_PageContext") -> None:
    entreprise = obtenir_entreprise()
    ctx.line(_DEVIS_LEFT, 93, _DEVIS_RIGHT, 93, color=(0.05, 0.05, 0.05), width=1.3)
    footer_1 = _join_parts(f"RC: {entreprise.rc}", f"IF: {entreprise.if_fiscal}", f"ICE: {entreprise.ice}", f"Patente: {entreprise.patente}", sep=" / ")
    footer_2 = f"Adresse: {_DEVIS_FOOTER_ADDRESS}"
    footer_3 = _join_parts(f"Tél: {entreprise.telephones}", f"E-mail : {entreprise.email}", sep=" / ")
    center_x = (_DEVIS_LEFT + _DEVIS_RIGHT) / 2
    _center_text(ctx, center_x, 82, footer_1, size=5.4)
    _center_text(ctx, center_x, 72, footer_2, size=5.4)
    _center_text(ctx, center_x, 62, footer_3, size=5.4)


def _draw_monster_cell(
    ctx: "_PageContext",
    x: float,
    y: float,
    width: float,
    height: float,
    value: object,
    *,
    size: float,
    bold: bool = False,
    align: str = "left",
) -> None:
    ctx.rect(x, y, width, height, stroke=_BLACK)
    text = "" if value is None else str(value)
    if not text:
        return
    fitted_size = _fit_font_size(text, size, max(4, width - 4), bold=bold)
    text_x = _aligned_text_x(x, width, text, fitted_size, align, bold=bold, padding=2)
    ctx.text(text_x, y + max(3.4, (height - fitted_size) / 2), text, size=fitted_size, bold=bold)


def _center_text(ctx: "_PageContext", center_x: float, y: float, text: object, *, size: float, bold: bool = False) -> None:
    value = _display(text)
    ctx.text(center_x - _estimated_text_width(value, size, bold=bold) / 2, y, value, size=size, bold=bold)


def _numero_devis_modele(devis: DevisReparation) -> str:
    return f"{devis.dossier.numero}-V{devis.version}"


def _etat_modele(ligne) -> str:
    if getattr(ligne, "type_ligne", None) == "main_oeuvre" or getattr(ligne, "etat_piece", None) == "mo":
        return "MO"
    if getattr(ligne, "etat_piece", None) == "occasion":
        return "OCC"
    if getattr(ligne, "etat_piece", None) == "autre":
        return str(getattr(ligne, "etat_piece_autre", "") or "AUTRE").upper()
    return "NEUF"


def _percent_label(rate: Decimal) -> str:
    return f"{int((Decimal(str(rate)) * 100).quantize(Decimal('1')))}%"


def _money_fr(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def _money_mad_compact(value) -> str:
    return f"{_money_fr(value)}MAD"


def _build_sntl_document_pdf(
    *,
    titre: str,
    numero: str,
    date_document,
    devis: DevisReparation,
    include_commission: bool,
    lignes=None,
    montant_ht=None,
    montant_tva=None,
    montant_ttc=None,
) -> bytes:
    pdf = _PdfDocument()
    ctx = _PageContext(pdf)
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    entreprise = obtenir_entreprise()
    tva = _param_percent("taux_tva", Decimal("20"))
    commission = _param_percent("taux_commission_sntl", Decimal("10"))

    _draw_sntl_header(ctx, titre, numero, date_document)
    _draw_sntl_partner_blocks(ctx, entreprise, dossier, client, vehicule)

    article_lines, labor_total = _split_sntl_lines(lignes if lignes is not None else devis.lignes)
    article_rows_count = max(10, len(article_lines))
    row_height = 13 if article_rows_count <= 10 else (11 if article_rows_count <= 18 else 9)
    body_size = 7 if article_rows_count <= 18 else 6
    totals_top, article_total = _draw_sntl_articles(ctx, 445, article_lines, article_rows_count, row_height, body_size)

    total_ht = Decimal(str(montant_ht)).quantize(Decimal("0.01")) if montant_ht is not None else (article_total + labor_total).quantize(Decimal("0.01"))
    montant_tva = Decimal(str(montant_tva)).quantize(Decimal("0.01")) if montant_tva is not None else (total_ht * tva).quantize(Decimal("0.01"))
    montant_ttc = Decimal(str(montant_ttc)).quantize(Decimal("0.01")) if montant_ttc is not None else (total_ht + montant_tva).quantize(Decimal("0.01"))
    commission_sntl = calculer_commission_sntl(total_ht, montant_ttc)

    totals = [
        ("Montant Total article HT", article_total, "wide"),
        ("Main d'œuvre*", labor_total, "short"),
        ("Montant Total article HT (1)", total_ht, "wide"),
        (f"TVA {int(tva * 100)}% (2)", montant_tva, "wide"),
        ("Montant Total TTC (1+2) (3)", montant_ttc, "wide"),
    ]
    if include_commission:
        totals.extend(
            [
                (f"Commission SNTL (1x{int(commission * 100)}%) (4)", commission_sntl.commission_ht, "wide"),
                (f"TVA {int(tva * 100)}% sur la commission (4x{int(tva * 100)}%) (5)", commission_sntl.tva_commission, "wide"),
                ("Montant Net à régler (3-4-5)", commission_sntl.net_a_regler, "wide"),
            ]
        )

    next_top = _draw_sntl_totals(ctx, totals_top, totals, row_height)
    phrase_subject = "la présente facture" if "FACTURE" in titre.upper() else "le présent devis"
    phrase = f"Arrêté {phrase_subject} à la somme de {_capitalize(_amount_to_french(montant_ttc))} TTC"
    ctx.text(_SNTL_X[2], next_top - 18, phrase, size=8)
    ctx.text(_SNTL_X[5], next_top - 58, "Cachet et signature", size=8)
    ctx.text(_SNTL_X[2], 56, "* Non valable pour les bons ateliers ''A\"", size=8)
    return pdf.render()


def _build_document_pdf(
    *,
    titre: str,
    numero: str,
    date_document,
    devis: DevisReparation,
    statut: str,
    montant_regle=None,
    lignes=None,
    montant_ht=None,
    montant_tva=None,
    montant_ttc=None,
) -> bytes:
    pdf = _PdfDocument()
    ctx = _PageContext(pdf)
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    entreprise = obtenir_entreprise()
    dossier_rows = [
        ("Dossier", dossier.numero),
        ("Statut", statut),
        ("Assurance", dossier.assurance_nom),
    ]
    if client.type == "sntl":
        dossier_rows.append(("Bon SNTL", dossier.numero_bon_sntl))
    elif dossier.numero_bon_sntl:
        dossier_rows.append(("N de bon", dossier.numero_bon_sntl))

    _draw_header(ctx, titre, numero, date_document)
    y = 690
    y = _draw_info_blocks(
        ctx,
        y,
        left_title="ATELIER",
        left_rows=[
            ("Raison sociale", entreprise.raison_sociale),
            ("Nom commercial", entreprise.nom_commercial),
            ("Adresse", entreprise.adresse),
            ("Téléphone", entreprise.telephones),
            ("ICE", entreprise.ice),
            ("RC / IF", _join_parts(entreprise.rc, entreprise.if_fiscal, sep=" / ")),
        ],
        right_title="CLIENT",
        right_rows=[
            ("Nom", client.nom),
            ("Type", client.type_libelle),
            ("Téléphone", client.telephone),
            ("Ville", client.ville),
            ("ICE", client.ice),
            ("Administration", client.administration_rattachee),
        ],
    )
    y = _draw_info_blocks(
        ctx,
        y - 12,
        left_title="VÉHICULE",
        left_rows=[
            ("Matricule", vehicule.immatriculation),
            ("Marque / modèle", f"{vehicule.marque} {vehicule.modele}"),
            ("Kilométrage", dossier.kilometrage_entree or vehicule.kilometrage_actuel),
        ],
        right_title="DOSSIER",
        right_rows=dossier_rows,
    )

    y -= 16
    lignes = list(lignes if lignes is not None else devis.lignes)
    montant_ht = devis.montant_ht if montant_ht is None else montant_ht
    montant_tva = devis.montant_tva if montant_tva is None else montant_tva
    montant_ttc = devis.montant_ttc if montant_ttc is None else montant_ttc
    y = _draw_lines_table(ctx, y, devis, lignes=lignes)
    y = _draw_totals(ctx, y - 14, montant_ht, montant_tva, montant_ttc, montant_regle=montant_regle)

    y -= 22
    if y < 130:
        ctx.new_page()
        y = 760
    ctx.text(_MARGIN, y, _arrete(montant_ttc), size=10, bold=True)
    if devis.notes:
        ctx.text(_MARGIN, y - 18, f"Notes: {devis.notes}", size=9)

    ctx.text(370, 88, "Cachet et signature", size=10, bold=True)
    ctx.line(350, 105, 530, 105)
    return pdf.render()


def _draw_header(ctx: "_PageContext", titre: str, numero: str, date_document) -> None:
    ctx.rect(_MARGIN, 742, 510, 58, fill=_SLATE)
    ctx.text(_MARGIN + 16, 778, "MONSTER GARAGE", size=22, bold=True, color=_YELLOW)
    ctx.text(_MARGIN + 17, 760, "WIDINE MOTORS SERVICES", size=10, bold=True, color=_WHITE)
    ctx.rect(_MARGIN, 706, 510, 30, fill=(1, 0.96, 0.7), stroke=_BLACK)
    ctx.text(_MARGIN + 14, 716, titre, size=14, bold=True)
    ctx.text(394, 716, f"N {numero}", size=10, bold=True)
    ctx.text(394, 698, f"Date: {_format_date(date_document)}", size=9)


def _draw_info_blocks(
    ctx: "_PageContext",
    y: float,
    *,
    left_title: str,
    left_rows: list[tuple[str, object]],
    right_title: str,
    right_rows: list[tuple[str, object]],
) -> float:
    block_width = 246
    left_x = _MARGIN
    right_x = _MARGIN + block_width + 18
    row_height = 15
    rows_count = max(len(left_rows), len(right_rows))
    block_height = 22 + rows_count * row_height

    for x, title, rows in ((left_x, left_title, left_rows), (right_x, right_title, right_rows)):
        ctx.rect(x, y - 16, block_width, 20, fill=_SLATE)
        ctx.text(x + 8, y - 10, title, size=9, bold=True, color=_YELLOW)
        ctx.rect(x, y - 16 - rows_count * row_height, block_width, rows_count * row_height, stroke=(0.75, 0.8, 0.86))
        row_y = y - 31
        for label, value in rows:
            ctx.text(x + 7, row_y, f"{label}:", size=7.5, bold=True, color=(0.38, 0.45, 0.55))
            ctx.text(x + 82, row_y, _display(value), size=7.5)
            row_y -= row_height
    return y - block_height


def _draw_lines_table(ctx: "_PageContext", y: float, devis: DevisReparation, *, lignes=None) -> float:
    columns = [
        ("REF", 48),
        ("DESIGNATION", 222),
        ("ETAT", 54),
        ("QTE", 46),
        ("PU HT", 70),
        ("TOTAL HT", 70),
    ]
    x_positions = [_MARGIN]
    for _, width in columns[:-1]:
        x_positions.append(x_positions[-1] + width)

    def header(current_y: float) -> float:
        ctx.rect(_MARGIN, current_y - 18, 510, 20, fill=_SLATE)
        for (label, _), x in zip(columns, x_positions):
            ctx.text(x + 5, current_y - 11, label, size=8, bold=True, color=_WHITE)
        return current_y - 24

    y = header(y)
    lignes = list(lignes if lignes is not None else devis.lignes)
    for index, ligne in enumerate(lignes, 1):
        wrapped = _wrap(ligne.designation, 44)
        row_height = max(20, 10 + len(wrapped) * 10)
        if y - row_height < 122:
            ctx.new_page()
            _draw_header(ctx, "SUITE", f"{devis.dossier.numero}-V{devis.version}", date.today())
            y = header(690)

        ctx.rect(_MARGIN, y - row_height + 5, 510, row_height, stroke=(0.82, 0.86, 0.9))
        ctx.text(x_positions[0] + 5, y - 7, f"REF-{index:03d}", size=8)
        line_y = y - 7
        for part in wrapped:
            ctx.text(x_positions[1] + 5, line_y, part, size=8)
            line_y -= 10
        ctx.text(x_positions[2] + 5, y - 7, ligne.etat_piece_libelle, size=8)
        ctx.text(x_positions[3] + 5, y - 7, _number(ligne.quantite), size=8)
        ctx.text(x_positions[4] + 5, y - 7, _money(ligne.prix_unitaire_ht), size=8)
        ctx.text(x_positions[5] + 5, y - 7, _money(ligne.total_ht), size=8, bold=True)
        y -= row_height
    return y


def _draw_totals(ctx: "_PageContext", y: float, montant_ht, montant_tva, montant_ttc, *, montant_regle=None) -> float:
    rows = [
        ("Montant HT", montant_ht),
        ("TVA", montant_tva),
        ("Montant TTC", montant_ttc),
    ]
    if montant_regle is not None:
        montant_regle = Decimal(str(montant_regle or 0)).quantize(Decimal("0.01"))
        reste = max(Decimal(str(montant_ttc or 0)) - montant_regle, Decimal("0.00"))
        rows.extend([("Montant encaissé", montant_regle), ("Reste à payer", reste)])

    x = 346
    for label, amount in rows:
        fill = (1, 0.96, 0.7) if label == "Montant TTC" else _LIGHT
        ctx.rect(x, y - 15, 206, 18, fill=fill, stroke=(0.75, 0.8, 0.86))
        ctx.text(x + 8, y - 9, label, size=8.5, bold=True)
        ctx.text(x + 126, y - 9, _money(amount), size=8.5, bold=True)
        y -= 19
    return y


def _draw_sntl_header(ctx: "_PageContext", titre: str, numero: str, date_document) -> None:
    ctx.text(_SNTL_X[2], 790, "MONSTER GARAGE", size=34, bold=True)
    ctx.line(_SNTL_X[2], 760, _SNTL_RIGHT, 760)

    is_facture = "FACTURE" in titre.upper()
    label = "Facture N°" if is_facture else "Devis N°"
    date_label = "Date facture:" if is_facture else "Date devis:"
    ctx.text(_SNTL_X[4], 718, label, size=10, bold=True)
    ctx.text(_SNTL_X[5] + 8, 718, numero, size=10, bold=True)
    ctx.text(_SNTL_X[6], 718, date_label, size=10, bold=True)
    ctx.text(_SNTL_X[7], 718, _format_date(date_document), size=10, bold=True)
    ctx.text(_SNTL_X[4] + 32, 692, "A", size=10)
    ctx.text(_SNTL_X[3] - 10, 660, _SNTL_DESTINATION, size=12, bold=True)


def _draw_sntl_partner_blocks(ctx: "_PageContext", entreprise, dossier, client, vehicule) -> None:
    top = 628
    row_height = 13
    _draw_sntl_cell(ctx, _SNTL_X[2], top, _SNTL_W[2] + _SNTL_W[3], row_height, "Partenaire", bold=True, align="center")
    _draw_sntl_cell(ctx, _SNTL_X[4], top, _SNTL_W[4] + _SNTL_W[5], row_height, "Véhicule", bold=True, align="center")
    _draw_sntl_cell(ctx, _SNTL_X[6], top, _SNTL_W[6] + _SNTL_W[7], row_height, "Partenaire", bold=True, align="center")

    partenaire_rows = [
        ("N° Agrément SNTL", entreprise.agrement_sntl),
        ("Raison Sociale", entreprise.raison_sociale),
        ("Adresse", entreprise.adresse),
        ("Ville", entreprise.ville),
        ("RC", entreprise.rc),
        ("Patente", entreprise.patente),
        ("IF", entreprise.if_fiscal),
        ("ICE", entreprise.ice),
        ("N° RIB", entreprise.rib),
    ]
    vehicle_rows = [
        ("Matricule", _format_sntl_matricule(vehicule.immatriculation)),
        ("Marque et modèle", f"{vehicule.marque} {vehicule.modele}".upper()),
        ("Kilométrage", dossier.kilometrage_entree or vehicule.kilometrage_actuel),
        ("Administration", (client.administration_rattachee or client.nom).upper()),
        ("N° de bon", _sntl_bon_number(dossier, client)),
    ]

    for index, (label, value) in enumerate(partenaire_rows):
        row_top = top - row_height * (index + 1)
        _draw_sntl_cell(ctx, _SNTL_X[2], row_top, _SNTL_W[2], row_height, label, size=7)
        _draw_sntl_cell(ctx, _SNTL_X[3], row_top, _SNTL_W[3], row_height, value, size=7, bold=True, wrap=True)

    for index, (label, value) in enumerate(vehicle_rows):
        row_top = top - row_height * (index + 1)
        _draw_sntl_cell(ctx, _SNTL_X[4], row_top, _SNTL_W[4], row_height, label, size=7)
        _draw_sntl_cell(ctx, _SNTL_X[5], row_top, _SNTL_W[5], row_height, value, size=7, bold=True, wrap=True)

    _draw_sntl_cell(ctx, _SNTL_X[6], top - row_height, _SNTL_W[6], row_height, "N° Accord SNTL", size=7)
    _draw_sntl_cell(ctx, _SNTL_X[7], top - row_height, _SNTL_W[7], row_height, "", size=7)


def _draw_sntl_articles(
    ctx: "_PageContext",
    top: float,
    article_lines,
    article_rows_count: int,
    row_height: float,
    body_size: float,
) -> tuple[float, Decimal]:
    headers = [
        (_SNTL_X[2], _SNTL_W[2], "Référence article"),
        (_SNTL_X[3], _SNTL_W[3] + _SNTL_W[4], "Désignation Article"),
        (_SNTL_X[5], _SNTL_W[5], "Quantité"),
        (_SNTL_X[6], _SNTL_W[6], "PU HT"),
        (_SNTL_X[7], _SNTL_W[7], "Total HT"),
    ]
    for x, width, label in headers:
        _draw_sntl_cell(ctx, x, top, width, row_height, label, size=7, align="center")

    article_total = Decimal("0.00")
    first_row_top = top - row_height
    for offset in range(article_rows_count):
        row_top = first_row_top - offset * row_height
        cells = [
            (_SNTL_X[2], _SNTL_W[2]),
            (_SNTL_X[3], _SNTL_W[3] + _SNTL_W[4]),
            (_SNTL_X[5], _SNTL_W[5]),
            (_SNTL_X[6], _SNTL_W[6]),
            (_SNTL_X[7], _SNTL_W[7]),
        ]
        for x, width in cells:
            _draw_sntl_cell(ctx, x, row_top, width, row_height, "", size=body_size)
        if offset >= len(article_lines):
            continue

        ligne = article_lines[offset]
        article_total += Decimal(str(ligne.total_ht or 0))
        _draw_sntl_cell(ctx, _SNTL_X[2], row_top, _SNTL_W[2], row_height, f"REF - N{offset + 1:03d}", size=body_size, align="center")
        _draw_sntl_cell(
            ctx,
            _SNTL_X[3],
            row_top,
            _SNTL_W[3] + _SNTL_W[4],
            row_height,
            str(ligne.designation or "").upper(),
            size=body_size,
            align="center",
            wrap=True,
        )
        _draw_sntl_cell(ctx, _SNTL_X[5], row_top, _SNTL_W[5], row_height, _number(ligne.quantite), size=body_size, align="center")
        _draw_sntl_cell(ctx, _SNTL_X[6], row_top, _SNTL_W[6], row_height, _sntl_money(ligne.prix_unitaire_ht), size=body_size, align="center")
        _draw_sntl_cell(ctx, _SNTL_X[7], row_top, _SNTL_W[7], row_height, _sntl_money(ligne.total_ht), size=body_size, align="center")

    return first_row_top - article_rows_count * row_height, article_total.quantize(Decimal("0.01"))


def _draw_sntl_totals(ctx: "_PageContext", top: float, rows: list[tuple[str, Decimal, str]], row_height: float) -> float:
    for index, (label, value, kind) in enumerate(rows):
        row_top = top - index * row_height
        if kind == "short":
            _draw_sntl_cell(ctx, _SNTL_X[2], row_top, _SNTL_W[2] + _SNTL_W[3] + _SNTL_W[4], row_height, label, size=7, align="center")
        else:
            _draw_sntl_cell(ctx, _SNTL_X[2], row_top, _SNTL_X[7] - _SNTL_X[2], row_height, label, size=7, align="right", padding=8)
        _draw_sntl_cell(ctx, _SNTL_X[7], row_top, _SNTL_W[7], row_height, _sntl_money(value), size=7, bold=True, align="right", padding=6)
    return top - len(rows) * row_height


def _draw_sntl_cell(
    ctx: "_PageContext",
    x: float,
    top: float,
    width: float,
    height: float,
    text: object = "",
    *,
    size=7,
    bold=False,
    align="left",
    wrap=False,
    padding=3,
) -> None:
    ctx.rect(x, top - height, width, height, stroke=_BLACK)
    value = "" if text is None else str(text)
    if not value:
        return

    available = max(4, width - padding * 2)
    fitted_size = _fit_font_size(value, size, available, bold=bold)
    lines = [value]
    if wrap and fitted_size <= 5 and _estimated_text_width(value, fitted_size, bold=bold) > available:
        max_chars = max(4, int(available / max(fitted_size * 0.58, 1)))
        lines = _wrap(value, max_chars)[:2]

    line_height = min(max(fitted_size + 1.2, 5.4), max(5.4, (height - 2) / max(len(lines), 1)))
    text_y = top - height + max(2.2, (height - line_height * len(lines)) / 2 + 2)
    for line_index, line in enumerate(reversed(lines)):
        text_x = _aligned_text_x(x, width, line, fitted_size, align, bold=bold, padding=padding)
        ctx.text(text_x, text_y + line_index * line_height, line, size=fitted_size, bold=bold)


def _fit_font_size(text: str, preferred_size: float, available_width: float, *, bold: bool = False) -> float:
    size = preferred_size
    while size > 4.6 and _estimated_text_width(text, size, bold=bold) > available_width:
        size -= 0.25
    return max(4.6, size)


def _aligned_text_x(x: float, width: float, text: str, size: float, align: str, *, bold: bool = False, padding: float = 3) -> float:
    estimated = _estimated_text_width(text, size, bold=bold)
    if align == "center":
        return x + max(2, (width - estimated) / 2)
    if align == "right":
        return x + max(2, width - estimated - padding)
    return x + padding


def _estimated_text_width(text: str, size: float, *, bold: bool = False) -> float:
    factor = 0.58 if bold else 0.55
    return len(str(text)) * size * factor


class _PageContext:
    def __init__(self, pdf: "_PdfDocument"):
        self.pdf = pdf
        self.commands: list[bytes] = []
        self.pdf.pages.append(self.commands)

    def new_page(self) -> None:
        self.commands = []
        self.pdf.pages.append(self.commands)

    def text(self, x: float, y: float, text: object, *, size=10, bold=False, italic=False, color=_BLACK) -> None:
        if bold and italic:
            font = "F4"
        elif italic:
            font = "F3"
        elif bold:
            font = "F2"
        else:
            font = "F1"
        self.commands.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg\nBT /{font} {size:.2f} Tf {x:.2f} {y:.2f} Td ".encode("ascii")
            + b"("
            + _pdf_text(text)
            + b") Tj ET\n"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float, color=_BLACK, *, width: float = 1) -> None:
        self.commands.append(f"{width:.2f} w\n{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG\n{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S\n".encode("ascii"))

    def rect(self, x: float, y: float, width: float, height: float, *, fill=None, stroke=None) -> None:
        if fill:
            self.commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg\n".encode("ascii"))
        if stroke:
            self.commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG\n".encode("ascii"))
        op = "B" if fill and stroke else ("f" if fill else "S")
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re {op}\n".encode("ascii"))

    def round_rect(self, x: float, y: float, width: float, height: float, radius: float, *, fill=None, stroke=None) -> None:
        k = 0.55228475
        r = min(radius, width / 2, height / 2)
        if fill:
            self.commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg\n".encode("ascii"))
        if stroke:
            self.commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG\n".encode("ascii"))
        path = (
            f"{x + r:.2f} {y:.2f} m "
            f"{x + width - r:.2f} {y:.2f} l "
            f"{x + width - r + k * r:.2f} {y:.2f} {x + width:.2f} {y + r - k * r:.2f} {x + width:.2f} {y + r:.2f} c "
            f"{x + width:.2f} {y + height - r:.2f} l "
            f"{x + width:.2f} {y + height - r + k * r:.2f} {x + width - r + k * r:.2f} {y + height:.2f} {x + width - r:.2f} {y + height:.2f} c "
            f"{x + r:.2f} {y + height:.2f} l "
            f"{x + r - k * r:.2f} {y + height:.2f} {x:.2f} {y + height - r + k * r:.2f} {x:.2f} {y + height - r:.2f} c "
            f"{x:.2f} {y + r:.2f} l "
            f"{x:.2f} {y + r - k * r:.2f} {x + r - k * r:.2f} {y:.2f} {x + r:.2f} {y:.2f} c h "
        )
        op = "B" if fill and stroke else ("f" if fill else "S")
        self.commands.append(f"{path}{op}\n".encode("ascii"))

    def image(self, path: Path, x: float, y: float, width: float, height: float) -> None:
        image_name = self.pdf.add_image(path)
        if not image_name:
            return
        self.commands.append(f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm /{image_name} Do Q\n".encode("ascii"))


class _PdfDocument:
    def __init__(self):
        self.pages: list[list[bytes]] = []
        self.images: dict[str, dict] = {}
        self._image_paths: dict[str, str] = {}

    def add_image(self, path: Path) -> str | None:
        key = str(path)
        if key in self._image_paths:
            return self._image_paths[key]
        if not path.exists():
            return None
        try:
            image = Image.open(path)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
        except Exception:
            return None

        name = f"Im{len(self.images) + 1}"
        self.images[name] = {
            "width": image.width,
            "height": image.height,
            "data": zlib.compress(image.tobytes()),
        }
        self._image_paths[key] = name
        return name

    def render(self) -> bytes:
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"",  # pages tree, filled after page objects are known
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-BoldOblique /Encoding /WinAnsiEncoding >>",
        ]
        image_object_ids = {}
        for name, image in self.images.items():
            object_id = len(objects) + 1
            image_object_ids[name] = object_id
            objects.append(
                (
                    f"<< /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} "
                    f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(image['data'])} >>\n"
                ).encode("ascii")
                + b"stream\n"
                + image["data"]
                + b"\nendstream"
            )

        xobjects = ""
        if image_object_ids:
            xobjects = " /XObject << " + " ".join(f"/{name} {object_id} 0 R" for name, object_id in image_object_ids.items()) + " >>"
        page_ids = []
        for commands in self.pages:
            content = b"".join(commands)
            content_id = len(objects) + 2
            page_id = len(objects) + 1
            page_ids.append(page_id)
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH:.2f} {_PAGE_HEIGHT:.2f}] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >>{xobjects} >> /Contents {content_id} 0 R >>".encode("ascii")
            )
            objects.append(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream")

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("ascii"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_at = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
        )
        return bytes(output)


def _pdf_text(value: object) -> bytes:
    text = _display(value)
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _wrap(value: object, width: int) -> list[str]:
    lines = textwrap.wrap(_display(value), width=width, break_long_words=False)
    return lines or ["-"]


def _display(value) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return date.today().strftime("%d/%m/%Y")


def _money(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f} MAD".replace(",", " ")


def _sntl_money(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ")


def _number(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount.normalize():f}"


def _join_parts(*parts, sep=", ") -> str:
    return sep.join(str(part) for part in parts if part)


def _arrete(amount) -> str:
    return f"Arrêté le présent document à la somme de {_money(amount)} TTC."


def _param_percent(cle: str, default: Decimal) -> Decimal:
    return param_percent(cle, default)


def _split_sntl_lines(lines) -> tuple[list, Decimal]:
    article_lines = []
    labor_total = Decimal("0.00")
    for line in lines:
        if getattr(line, "type_ligne", None) == "main_oeuvre" or _is_labor_line(line.designation):
            labor_total += Decimal(str(line.total_ht or 0))
        else:
            article_lines.append(line)
    return article_lines, labor_total.quantize(Decimal("0.01"))


def _is_labor_line(designation: str) -> bool:
    normalized = (designation or "").lower().replace("\u0153", "oe").replace("Å“", "oe")
    return "main" in normalized and ("oeuvre" in normalized or "d'oeuvre" in normalized or "d oeuvre" in normalized)


def _format_sntl_matricule(value: object) -> str:
    raw = str(value or "").strip().upper()
    compact = re.sub(r"\s+", "", raw)
    match = re.fullmatch(r"([A-Z])[- ]?(\d+)", compact)
    if match:
        letter, number = match.groups()
        return f"{number.zfill(7)} - {letter}"

    match = re.fullmatch(r"(\d+)[- ]?([A-Z])", compact)
    if match:
        number, letter = match.groups()
        return f"{number.zfill(7)} - {letter}"

    return raw


def _sntl_bon_number(dossier, client) -> str:
    if getattr(dossier, "numero_bon_sntl", None):
        return dossier.numero_bon_sntl

    candidates = [dossier.notes, client.notes, dossier.numero]
    for candidate in candidates:
        text = str(candidate or "")
        match = re.search(r"(?:bon|or|ordre|n[°o])\D*(\d[\d\s-]*)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return dossier.numero


def _amount_to_french(amount: Decimal) -> str:
    amount = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    dirhams = int(amount)
    centimes = int((amount - Decimal(dirhams)) * 100)
    words = f"{_number_to_french(dirhams)} dirhams"
    if centimes:
        words += f" et {_number_to_french(centimes)} centimes"
    return words


def _number_to_french(number: int) -> str:
    if number == 0:
        return "zero"

    units = [
        "",
        "un",
        "deux",
        "trois",
        "quatre",
        "cinq",
        "six",
        "sept",
        "huit",
        "neuf",
        "dix",
        "onze",
        "douze",
        "treize",
        "quatorze",
        "quinze",
        "seize",
    ]
    tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}

    def below_hundred(value: int) -> str:
        if value < 17:
            return units[value]
        if value < 20:
            return f"dix {units[value - 10]}"
        if value < 70:
            ten = (value // 10) * 10
            rest = value % 10
            if rest == 0:
                return tens[ten]
            sep = " et " if rest == 1 else " "
            return f"{tens[ten]}{sep}{units[rest]}"
        if value < 80:
            rest = value - 60
            sep = " et " if rest == 11 else " "
            return f"soixante{sep}{below_hundred(rest)}"
        rest = value - 80
        if rest == 0:
            return "quatre vingt"
        return f"quatre vingt {below_hundred(rest)}"

    def below_thousand(value: int) -> str:
        if value < 100:
            return below_hundred(value)
        hundred = value // 100
        rest = value % 100
        prefix = "cent" if hundred == 1 else f"{units[hundred]} cent"
        return prefix if rest == 0 else f"{prefix} {below_hundred(rest)}"

    chunks = []
    millions = number // 1_000_000
    if millions:
        chunks.append("un million" if millions == 1 else f"{below_thousand(millions)} millions")
        number %= 1_000_000
    thousands = number // 1000
    if thousands:
        chunks.append("mille" if thousands == 1 else f"{below_thousand(thousands)} mille")
        number %= 1000
    if number:
        chunks.append(below_thousand(number))
    return " ".join(chunks)


def _capitalize(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "document.pdf"

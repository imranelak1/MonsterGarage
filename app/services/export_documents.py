from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import re

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models import Client, DevisReparation, FactureReparation, ParametreSysteme
from app.services.parametres import obtenir_entreprise


XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_JAUNE = "FFFFD700"
_NOIR = "FF000000"
_BLANC = "FFFFFFFF"
_SLATE_950 = "FF020617"
_SLATE_100 = "FFF1F5F9"
_SLATE_200 = "FFE2E8F0"
_SLATE_500 = "FF64748B"
_AMBRE_PALE = "FFFFF7CC"
_VERT_PALE = "FFEAF7EE"
_ROUGE_PALE = "FFFFECEC"
_LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "img" / "logo_monster_garage.png"


def exporter_devis_excel(devis: DevisReparation) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"DEVIS V{devis.version}"
    _document_setup(ws)
    is_sntl = devis.dossier.client.type == "sntl"
    _build_document_reparation(
        ws,
        titre="DEVIS SNTL" if is_sntl else "DEVIS DE REPARATION",
        numero=f"{devis.dossier.numero}-V{devis.version}",
        date_document=devis.created_at,
        devis=devis,
        statut=devis.statut_libelle,
        hide_etat=is_sntl,
        include_commission_sntl=False,
    )
    return _save(wb)


def exporter_facture_excel(facture: FactureReparation) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = _safe_sheet_title(facture.numero)
    _document_setup(ws)

    if facture.dossier.client.type == "sntl":
        _build_document_reparation(
            ws,
            titre="FACTURE SNTL",
            numero=facture.numero,
            date_document=facture.created_at,
            devis=facture.devis,
            statut=facture.statut_libelle,
            montant_regle=facture.montant_regle,
            hide_etat=True,
            include_commission_sntl=True,
        )
    else:
        _build_document_reparation(
            ws,
            titre="FACTURE",
            numero=facture.numero,
            date_document=facture.created_at,
            devis=facture.devis,
            statut=facture.statut_libelle,
            montant_regle=facture.montant_regle,
            hide_etat=False,
            include_commission_sntl=False,
        )
    return _save(wb)


def exporter_releve_client_excel(client: Client, factures: list[FactureReparation]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "SITUATION CLIENT"
    _document_setup(ws, widths=[18, 28, 24, 18, 18, 18, 18, 18])
    _build_header(ws, f"SITUATION {client.nom.upper()}", client.type_libelle.upper(), date.today())

    ws.merge_cells("A6:D6")
    ws["A6"].value = "WIDINE MOTORS SERVICES"
    ws["A6"].font = _font(bold=True, size=12, color=_SLATE_950)
    ws["A6"].alignment = _align("center")

    headers = ["N FACTURE", "VEHICULE", "IMMATRICULATION", "MONTANT FACTURE", "ENCAISSE", "A ENCAISSER", "DATE", "STATUT"]
    header_row = 9
    for col, value in enumerate(headers, 1):
        cell = ws.cell(header_row, col, value)
        cell.fill = _fill(_SLATE_950)
        cell.font = _font(bold=True, color=_BLANC)
        cell.alignment = _align("center", wrap=True)
        cell.border = _border()

    first_data_row = header_row + 1
    for index, facture in enumerate(factures, first_data_row):
        vehicule = facture.dossier.vehicule
        encaisse = facture.montant_regle or Decimal("0.00")
        values = [
            facture.numero,
            f"{vehicule.marque} {vehicule.modele}",
            vehicule.immatriculation,
            _money(facture.montant_ttc),
            _money(encaisse),
            f"=D{index}-E{index}",
            _date_value(facture.created_at),
            facture.statut_libelle,
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(index, col, value)
            cell.border = _border("FFCBD5E1")
            cell.alignment = _align("center" if col != 2 else "left", wrap=True)
            if col in {4, 5, 6}:
                cell.number_format = '#,##0.00 "MAD"'

    total_row = max(first_data_row, first_data_row + len(factures)) + 1
    ws.cell(total_row, 3, "TOTAL").font = _font(bold=True, size=12)
    for col in (4, 5, 6):
        cell = ws.cell(total_row, col, f"=SUM({get_column_letter(col)}{first_data_row}:{get_column_letter(col)}{total_row - 1})")
        cell.font = _font(bold=True, size=12)
        cell.fill = _fill(_AMBRE_PALE)
        cell.border = _border()
        cell.number_format = '#,##0.00 "MAD"'

    _set_print_options(ws)
    return _save(wb)


def nom_fichier_devis(devis: DevisReparation) -> str:
    return _safe_filename(f"DEVIS_{devis.dossier.numero}_V{devis.version}.xlsx")


def nom_fichier_facture(facture: FactureReparation) -> str:
    prefix = "FACTURE_SNTL" if facture.dossier.client.type == "sntl" else "FACTURE"
    return _safe_filename(f"{prefix}_{facture.numero}.xlsx")


def nom_fichier_releve_client(client: Client) -> str:
    return _safe_filename(f"RELEVE_SITUATION_{client.nom}.xlsx")


def _build_document_reparation(
    ws,
    *,
    titre: str,
    numero: str,
    date_document,
    devis: DevisReparation,
    statut: str,
    include_commission_sntl: bool,
    hide_etat: bool,
    montant_regle=None,
) -> None:
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    entreprise = obtenir_entreprise()

    _build_header(ws, titre, numero, date_document)

    ws.merge_cells("A6:C6")
    ws["A6"].value = "ATELIER"
    ws.merge_cells("E6:G6")
    ws["E6"].value = "CLIENT"
    for cell in (ws["A6"], ws["E6"]):
        cell.fill = _fill(_SLATE_950)
        cell.font = _font(bold=True, color=_JAUNE)
        cell.alignment = _align("center")
        cell.border = _border()

    atelier = [
        ("Raison sociale", entreprise.raison_sociale),
        ("Adresse", entreprise.adresse),
        ("Ville", entreprise.ville),
        ("Telephone", entreprise.telephones),
        ("ICE", entreprise.ice),
        ("RC / IF", _join_parts(entreprise.rc, entreprise.if_fiscal, sep=" / ")),
        ("RIB", entreprise.rib),
    ]
    client_infos = [
        ("Nom", client.nom),
        ("Type", client.type_libelle),
        ("Telephone", client.telephone),
        ("Adresse", client.adresse),
        ("Ville", client.ville),
        ("ICE", client.ice),
        ("Administration", client.administration_rattachee),
    ]
    for row_offset, (label, value) in enumerate(atelier, 7):
        _label_value(ws, row_offset, 1, label, value, width=3)
    for row_offset, (label, value) in enumerate(client_infos, 7):
        _label_value(ws, row_offset, 5, label, value, width=3)

    vehicle_row = 16
    ws.merge_cells(start_row=vehicle_row, start_column=1, end_row=vehicle_row, end_column=7)
    ws.cell(vehicle_row, 1, "VEHICULE").fill = _fill(_SLATE_950)
    ws.cell(vehicle_row, 1).font = _font(bold=True, color=_JAUNE)
    ws.cell(vehicle_row, 1).alignment = _align("center")
    _style_range(ws, vehicle_row, 1, vehicle_row, 7, border=_border())

    vehicle_infos = [
        ("Matricule", vehicule.immatriculation),
        ("Marque et modele", f"{vehicule.marque} {vehicule.modele}"),
        ("Kilometrage", dossier.kilometrage_entree or vehicule.kilometrage_actuel),
        ("Dossier", dossier.numero),
        ("Statut", statut),
        ("Assurance", dossier.assurance_nom),
    ]
    for col_index, (label, value) in enumerate(vehicle_infos, 1):
        row = 17 + ((col_index - 1) // 3)
        col = 1 + ((col_index - 1) % 3) * 2
        _label_value(ws, row, col, label, value, width=2)

    table_row = 21
    if hide_etat:
        headers = ["REFERENCE", "DESIGNATION", "QTE", "PU HT", "TOTAL HT"]
        table_columns = [1, 2, 5, 6, 7]
    else:
        headers = ["REFERENCE", "DESIGNATION", "ETAT", "QTE", "PU HT", "TOTAL HT"]
        table_columns = [1, 2, 4, 5, 6, 7]
    for col, header in zip(table_columns, headers):
        cell = ws.cell(table_row, col, header)
        cell.fill = _fill(_SLATE_950)
        cell.font = _font(bold=True, color=_BLANC)
        cell.alignment = _align("center", wrap=True)
        cell.border = _border()
    designation_end_col = 4 if hide_etat else 3
    ws.merge_cells(start_row=table_row, start_column=2, end_row=table_row, end_column=designation_end_col)

    first_line_row = table_row + 1
    for index, ligne in enumerate(devis.lignes, first_line_row):
        if hide_etat:
            values = [
                f"REF-{index - table_row:03d}",
                ligne.designation,
                _money(ligne.quantite),
                _money(ligne.prix_unitaire_ht),
                _money(ligne.total_ht),
            ]
        else:
            values = [
                f"REF-{index - table_row:03d}",
                ligne.designation,
                ligne.etat_piece_libelle,
                _money(ligne.quantite),
                _money(ligne.prix_unitaire_ht),
                _money(ligne.total_ht),
            ]
        for col, value in zip(table_columns, values):
            cell = ws.cell(index, col, value)
            cell.border = _border("FFCBD5E1")
            cell.alignment = _align("center" if col != 2 else "left", wrap=True)
            if (hide_etat and col == 5) or (not hide_etat and col == 5):
                cell.number_format = "0.##"
            if col in {6, 7}:
                cell.number_format = '#,##0.00 "MAD"'
        ws.merge_cells(start_row=index, start_column=2, end_row=index, end_column=designation_end_col)

    last_line_row = max(first_line_row, first_line_row + len(devis.lignes) - 1)
    totals_row = last_line_row + 2
    _totals_block(
        ws,
        totals_row,
        devis.montant_ht,
        devis.montant_tva,
        devis.montant_ttc,
        montant_regle=montant_regle,
        include_commission_sntl=include_commission_sntl,
    )

    note_row = totals_row + (10 if include_commission_sntl else 7)
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=7)
    ws.cell(note_row, 1, _arrete(float(devis.montant_ttc))).alignment = _align("left", wrap=True)
    ws.cell(note_row, 1).font = _font(bold=True, size=10)

    if devis.notes:
        ws.merge_cells(start_row=note_row + 2, start_column=1, end_row=note_row + 3, end_column=7)
        ws.cell(note_row + 2, 1, f"Notes: {devis.notes}").alignment = _align("left", wrap=True)
        _style_range(ws, note_row + 2, 1, note_row + 3, 7, fill=_fill(_SLATE_100), border=_border("FFCBD5E1"))

    ws.merge_cells(start_row=note_row + 5, start_column=5, end_row=note_row + 5, end_column=7)
    ws.cell(note_row + 5, 5, "Cachet et signature").font = _font(bold=True)
    ws.cell(note_row + 5, 5).alignment = _align("center")

    _set_print_options(ws)


def _totals_block(
    ws,
    start_row: int,
    montant_ht,
    montant_tva,
    montant_ttc,
    *,
    include_commission_sntl: bool,
    montant_regle=None,
) -> None:
    tva = _param_percent("taux_tva", Decimal("20"))
    commission = _param_percent("taux_commission_sntl", Decimal("10"))
    montant_ht = Decimal(str(montant_ht or 0)).quantize(Decimal("0.01"))
    montant_tva = Decimal(str(montant_tva or 0)).quantize(Decimal("0.01"))
    montant_ttc = Decimal(str(montant_ttc or 0)).quantize(Decimal("0.01"))
    commission_sntl = (montant_ht * commission).quantize(Decimal("0.01"))
    tva_commission = (commission_sntl * tva).quantize(Decimal("0.01"))
    net_a_regler = (montant_ttc - commission_sntl - tva_commission).quantize(Decimal("0.01"))

    rows = [
        ("Montant HT", _money(montant_ht), _SLATE_100),
        (f"TVA {int(tva * 100)}%", _money(montant_tva), _SLATE_100),
        ("Montant TTC", _money(montant_ttc), _AMBRE_PALE),
    ]
    if montant_regle is not None:
        montant_regle = Decimal(str(montant_regle or 0)).quantize(Decimal("0.01"))
        reste = max(montant_ttc - montant_regle, Decimal("0.00"))
        rows.extend(
            [
                ("Montant encaisse", _money(montant_regle), _VERT_PALE),
                ("Reste a payer", _money(reste), _ROUGE_PALE if reste else _VERT_PALE),
            ]
        )
    if include_commission_sntl:
        rows.extend(
            [
                (f"Commission SNTL {int(commission * 100)}%", _money(commission_sntl), _ROUGE_PALE),
                (f"TVA {int(tva * 100)}% sur commission", _money(tva_commission), _ROUGE_PALE),
                ("Montant net a regler", _money(net_a_regler), _VERT_PALE),
            ]
        )

    for index, (label, value, fill_color) in enumerate(rows, start_row):
        ws.merge_cells(start_row=index, start_column=1, end_row=index, end_column=6)
        ws.cell(index, 1, label)
        ws.cell(index, 7, value)
        _style_range(ws, index, 1, index, 7, fill=_fill(fill_color), border=_border(), alignment=_align("right"))
        ws.cell(index, 1).font = _font(bold=True)
        ws.cell(index, 7).font = _font(bold=True)
        ws.cell(index, 7).number_format = '#,##0.00 "MAD"'


def _build_header(ws, titre: str, numero: str, date_document) -> None:
    for row in range(1, 5):
        ws.row_dimensions[row].height = 24

    ws.merge_cells("A1:B4")
    _style_range(ws, 1, 1, 4, 2, fill=_fill(_SLATE_950), border=_border(), alignment=_align("center"))
    _add_logo(ws)

    ws.merge_cells("C1:G2")
    ws["C1"].value = "MONSTER GARAGE"
    ws["C1"].font = _font(bold=True, size=24, color=_JAUNE)
    ws["C1"].alignment = _align("center")
    _style_range(ws, 1, 3, 2, 7, fill=_fill(_SLATE_950), border=_border(), alignment=_align("center"))

    ws.merge_cells("C3:G3")
    ws["C3"].value = "WIDINE MOTORS SERVICES"
    ws["C3"].font = _font(bold=True, size=13, color=_BLANC)
    ws["C3"].alignment = _align("center")
    _style_range(ws, 3, 3, 3, 7, fill=_fill(_SLATE_950), border=_border(), alignment=_align("center"))

    ws.merge_cells("C4:E4")
    ws["C4"].value = titre
    ws["C4"].font = _font(bold=True, size=14, color=_SLATE_950)
    ws["C4"].alignment = _align("center")
    ws["F4"].value = "N"
    ws["G4"].value = numero
    for cell in ("C4", "F4", "G4"):
        ws[cell].fill = _fill(_AMBRE_PALE)
        ws[cell].border = _border()
        ws[cell].alignment = _align("center")
        ws[cell].font = _font(bold=True)

    ws["F5"].value = "Date"
    ws["G5"].value = _date_value(date_document)
    ws["G5"].number_format = "dd/mm/yyyy"
    for cell in ("F5", "G5"):
        ws[cell].border = _border()
        ws[cell].alignment = _align("center")
        ws[cell].font = _font(bold=True)


def _document_setup(ws, widths=None) -> None:
    widths = widths or [16, 28, 18, 18, 12, 16, 18]
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.35
    ws.page_margins.bottom = 0.35


def _label_value(ws, row: int, col: int, label: str, value, *, width: int) -> None:
    ws.cell(row, col, label)
    ws.cell(row, col + 1, _display(value))
    if width > 2:
        ws.merge_cells(start_row=row, start_column=col + 1, end_row=row, end_column=col + width - 1)
    ws.cell(row, col).font = _font(bold=True, color=_SLATE_500)
    ws.cell(row, col).alignment = _align("left", wrap=True)
    ws.cell(row, col + 1).alignment = _align("left", wrap=True)
    _style_range(ws, row, col, row, col + width - 1, border=_border("FFCBD5E1"))


def _add_logo(ws) -> None:
    if not _LOGO_PATH.exists():
        return
    logo = XLImage(str(_LOGO_PATH))
    logo.width = 150
    logo.height = 70
    logo.anchor = "A1"
    ws.add_image(logo)


def _set_print_options(ws) -> None:
    ws.print_title_rows = "1:5"


def _style_range(ws, min_row: int, min_col: int, max_row: int, max_col: int, *, fill=None, border=None, alignment=None) -> None:
    for row in ws.iter_rows(min_row=min_row, min_col=min_col, max_row=max_row, max_col=max_col):
        for cell in row:
            if fill:
                cell.fill = fill
            if border:
                cell.border = border
            if alignment:
                cell.alignment = alignment


def _save(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _param_percent(cle: str, default: Decimal) -> Decimal:
    param = ParametreSysteme.query.filter_by(cle=cle).first()
    raw = param.valeur if param else default
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        value = default
    return (value / Decimal("100")).quantize(Decimal("0.0001"))


def _money(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _display(value) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _join_parts(*parts, sep=", ") -> str:
    return sep.join(str(part) for part in parts if part)


def _arrete(amount: float) -> str:
    return f"Arrete le present document a la somme de {amount:,.2f} dirhams TTC.".replace(",", " ")


def _safe_sheet_title(value: str) -> str:
    return re.sub(r"[\[\]\:\*\?\/\\]", "-", value)[:31] or "DOCUMENT"


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "document.xlsx"


def _font(*, bold=False, size=10, color=_NOIR, name="Calibri") -> Font:
    return Font(name=name, bold=bold, size=size, color=color)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _border(color=_NOIR) -> Border:
    side = Side(style="thin", color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def _align(horizontal="left", *, wrap=False) -> Alignment:
    return Alignment(horizontal=horizontal, vertical="center", wrap_text=wrap)

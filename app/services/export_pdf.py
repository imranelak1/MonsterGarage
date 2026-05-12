from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
import textwrap

from app.models import DevisReparation, FactureReparation
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


def exporter_devis_pdf(devis: DevisReparation) -> bytes:
    titre = "DEVIS SNTL" if devis.dossier.client.type == "sntl" else "DEVIS DE REPARATION"
    numero = f"{devis.dossier.numero}-V{devis.version}"
    return _build_document_pdf(
        titre=titre,
        numero=numero,
        date_document=devis.created_at,
        devis=devis,
        statut=devis.statut_libelle,
    )


def exporter_facture_pdf(facture: FactureReparation) -> bytes:
    if facture.dossier.client.type == "sntl":
        titre = "FACTURE SNTL"
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
        montant_regle=facture.montant_regle,
    )


def nom_fichier_devis_pdf(devis: DevisReparation) -> str:
    return _safe_filename(f"DEVIS_{devis.dossier.numero}_V{devis.version}.pdf")


def nom_fichier_facture_pdf(facture: FactureReparation) -> str:
    prefix = "FACTURE_SNTL" if facture.dossier.client.type == "sntl" else "FACTURE"
    return _safe_filename(f"{prefix}_{facture.numero}.pdf")


def _build_document_pdf(
    *,
    titre: str,
    numero: str,
    date_document,
    devis: DevisReparation,
    statut: str,
    montant_regle=None,
) -> bytes:
    pdf = _PdfDocument()
    ctx = _PageContext(pdf)
    dossier = devis.dossier
    client = dossier.client
    vehicule = dossier.vehicule
    entreprise = obtenir_entreprise()

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
            ("Telephone", entreprise.telephones),
            ("ICE", entreprise.ice),
            ("RC / IF", _join_parts(entreprise.rc, entreprise.if_fiscal, sep=" / ")),
        ],
        right_title="CLIENT",
        right_rows=[
            ("Nom", client.nom),
            ("Type", client.type_libelle),
            ("Telephone", client.telephone),
            ("Ville", client.ville),
            ("ICE", client.ice),
            ("Administration", client.administration_rattachee),
        ],
    )
    y = _draw_info_blocks(
        ctx,
        y - 12,
        left_title="VEHICULE",
        left_rows=[
            ("Matricule", vehicule.immatriculation),
            ("Marque / modele", f"{vehicule.marque} {vehicule.modele}"),
            ("Kilometrage", dossier.kilometrage_entree or vehicule.kilometrage_actuel),
        ],
        right_title="DOSSIER",
        right_rows=[
            ("Dossier", dossier.numero),
            ("Statut", statut),
            ("Assurance", dossier.assurance_nom),
            ("Bon SNTL", dossier.numero_bon_sntl),
        ],
    )

    y -= 16
    y = _draw_lines_table(ctx, y, devis)
    y = _draw_totals(ctx, y - 14, devis, montant_regle=montant_regle)

    y -= 22
    if y < 130:
        ctx.new_page()
        y = 760
    ctx.text(_MARGIN, y, _arrete(devis.montant_ttc), size=10, bold=True)
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


def _draw_lines_table(ctx: "_PageContext", y: float, devis: DevisReparation) -> float:
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
    for index, ligne in enumerate(devis.lignes, 1):
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


def _draw_totals(ctx: "_PageContext", y: float, devis: DevisReparation, *, montant_regle=None) -> float:
    rows = [
        ("Montant HT", devis.montant_ht),
        ("TVA", devis.montant_tva),
        ("Montant TTC", devis.montant_ttc),
    ]
    if montant_regle is not None:
        montant_regle = Decimal(str(montant_regle or 0)).quantize(Decimal("0.01"))
        reste = max(Decimal(str(devis.montant_ttc or 0)) - montant_regle, Decimal("0.00"))
        rows.extend([("Montant encaisse", montant_regle), ("Reste a payer", reste)])

    x = 346
    for label, amount in rows:
        fill = (1, 0.96, 0.7) if label == "Montant TTC" else _LIGHT
        ctx.rect(x, y - 15, 206, 18, fill=fill, stroke=(0.75, 0.8, 0.86))
        ctx.text(x + 8, y - 9, label, size=8.5, bold=True)
        ctx.text(x + 126, y - 9, _money(amount), size=8.5, bold=True)
        y -= 19
    return y


class _PageContext:
    def __init__(self, pdf: "_PdfDocument"):
        self.pdf = pdf
        self.commands: list[bytes] = []
        self.pdf.pages.append(self.commands)

    def new_page(self) -> None:
        self.commands = []
        self.pdf.pages.append(self.commands)

    def text(self, x: float, y: float, text: object, *, size=10, bold=False, color=_BLACK) -> None:
        font = "F2" if bold else "F1"
        self.commands.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg\nBT /{font} {size:.2f} Tf {x:.2f} {y:.2f} Td ".encode("ascii")
            + b"("
            + _pdf_text(text)
            + b") Tj ET\n"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float, color=_BLACK) -> None:
        self.commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG\n{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S\n".encode("ascii"))

    def rect(self, x: float, y: float, width: float, height: float, *, fill=None, stroke=None) -> None:
        if fill:
            self.commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg\n".encode("ascii"))
        if stroke:
            self.commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG\n".encode("ascii"))
        op = "B" if fill and stroke else ("f" if fill else "S")
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re {op}\n".encode("ascii"))


class _PdfDocument:
    def __init__(self):
        self.pages: list[list[bytes]] = []

    def render(self) -> bytes:
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"",  # pages tree, filled after page objects are known
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ]
        page_ids = []
        for commands in self.pages:
            content = b"".join(commands)
            content_id = len(objects) + 2
            page_id = len(objects) + 1
            page_ids.append(page_id)
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH:.2f} {_PAGE_HEIGHT:.2f}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
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


def _number(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount.normalize():f}"


def _join_parts(*parts, sep=", ") -> str:
    return sep.join(str(part) for part in parts if part)


def _arrete(amount) -> str:
    return f"Arrete le present document a la somme de {_money(amount)} TTC."


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "document.pdf"

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from app.models import DossierReparation
from app.services.export_pdf import _PageContext, _PdfDocument
from app.services.parametres import obtenir_entreprise


DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_TEMPLATE_PATH = Path(__file__).resolve().parent / "resources" / "attestation_immobilisation.docx"
_LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "img" / "logo_monster_garage.png"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_MONSTER_BLUE = (0.02, 0.43, 0.72)
_BLACK = (0, 0, 0)
_PAGE_WIDTH = 595.28
_HELVETICA_WIDTHS = {
    " ": 278,
    "!": 278,
    '"': 355,
    "#": 556,
    "$": 556,
    "%": 889,
    "&": 667,
    "'": 222,
    "(": 333,
    ")": 333,
    "*": 389,
    "+": 584,
    ",": 278,
    "-": 333,
    ".": 278,
    "/": 278,
    "0": 556,
    "1": 556,
    "2": 556,
    "3": 556,
    "4": 556,
    "5": 556,
    "6": 556,
    "7": 556,
    "8": 556,
    "9": 556,
    ":": 278,
    ";": 278,
    "<": 584,
    "=": 584,
    ">": 584,
    "?": 556,
    "@": 1015,
    "A": 667,
    "B": 667,
    "C": 722,
    "D": 722,
    "E": 667,
    "F": 611,
    "G": 778,
    "H": 722,
    "I": 278,
    "J": 500,
    "K": 667,
    "L": 556,
    "M": 833,
    "N": 722,
    "O": 778,
    "P": 667,
    "Q": 778,
    "R": 722,
    "S": 667,
    "T": 611,
    "U": 722,
    "V": 667,
    "W": 944,
    "X": 667,
    "Y": 667,
    "Z": 611,
    "[": 278,
    "\\": 278,
    "]": 278,
    "^": 469,
    "_": 556,
    "`": 222,
    "a": 556,
    "b": 556,
    "c": 500,
    "d": 556,
    "e": 556,
    "f": 278,
    "g": 556,
    "h": 556,
    "i": 222,
    "j": 222,
    "k": 500,
    "l": 222,
    "m": 833,
    "n": 556,
    "o": 556,
    "p": 556,
    "q": 556,
    "r": 333,
    "s": 500,
    "t": 278,
    "u": 556,
    "v": 500,
    "w": 722,
    "x": 500,
    "y": 500,
    "z": 500,
    "{": 334,
    "|": 260,
    "}": 334,
    "~": 584,
    "°": 400,
    "’": 222,
}

ET.register_namespace("w", _W_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")


def nom_fichier_attestation(dossier: DossierReparation, extension: str) -> str:
    return f"ATTESTATION_IMMOBILISATION_{dossier.numero}.{extension}"


def exporter_attestation_pdf(dossier: DossierReparation, jours_reparation: int = 7) -> bytes:
    entreprise = obtenir_entreprise()
    pdf = _PdfDocument()
    ctx = _PageContext(pdf)
    _dessiner_entete_attestation(ctx)
    _dessiner_corps_attestation(ctx, dossier, entreprise, jours_reparation)
    _dessiner_pied_attestation(ctx, entreprise)
    return pdf.render()


def exporter_attestation_docx(dossier: DossierReparation, jours_reparation: int = 7) -> bytes:
    entreprise = obtenir_entreprise()
    document_xml = _document_xml_depuis_modele(dossier, entreprise, jours_reparation)
    buffer = BytesIO()
    with ZipFile(_TEMPLATE_PATH, "r") as template, ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
        for item in template.infolist():
            data = document_xml if item.filename == "word/document.xml" else template.read(item.filename)
            docx.writestr(item, data)
    return buffer.getvalue()


def _paragraphes_attestation(dossier: DossierReparation, entreprise, jours_reparation: int) -> tuple[str, ...]:
    vehicule = dossier.vehicule
    depot = _format_date(dossier.created_at)
    ville = entreprise.ville or "Marrakech"
    return (
        (
            f"Nous soussignés, Société {entreprise.raison_sociale}, {entreprise.nom_commercial}, "
            f"immatriculée au RC Marrakech sous le numéro {entreprise.rc} domiciliée au {entreprise.adresse}, "
            f"{ville}, représentée par son gérant M. AMINE ERRARAY."
        ),
        (
            f"Attestons par la présente que le véhicule de marque {vehicule.marque} {vehicule.modele} "
            f"immatriculé {vehicule.immatriculation}  a été déposé au sein de notre atelier en date du {depot} "
            f"pour réparation suite à une panne."
        ),
        f"Le délai de réparation initial estimé est de {_format_jours(jours_reparation)} Jours à partir de la date de dépôt",
        "Cette attestation est délivrée de bonne foi à la demande de l’intéressée pour servir et valoir ce que de droit.",
        _ligne_fait_a(entreprise),
    )


def _format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return date.today().strftime("%d/%m/%Y")


def _format_jours(value: int) -> str:
    return f"{max(int(value or 1), 1):02d}"


def _ligne_fait_a(entreprise) -> str:
    return f"Fait à {entreprise.ville or 'Marrakech'}, le {_format_date(date.today())}"


def _dessiner_entete_attestation(ctx: _PageContext) -> None:
    ctx.text(75, 742, "MONSTER GARAGE", size=35, bold=True, italic=True, color=_MONSTER_BLUE)
    ctx.line(75, 736, 444, 736, color=_MONSTER_BLUE, width=1.3)
    ctx.image(_LOGO_PATH, 460, 726, 116, 54)
    ctx.line(70, 708, 595, 708, color=_BLACK, width=1.2)


def _dessiner_corps_attestation(
    ctx: _PageContext,
    dossier: DossierReparation,
    entreprise,
    jours_reparation: int,
) -> None:
    vehicule = dossier.vehicule
    depot = _format_date(dossier.created_at)
    ville = entreprise.ville or "Marrakech"
    titre = "ATTESTATION D’IMMOBILISATION"

    title_size = 12
    title_x = _center_x(titre, title_size, bold=True)
    ctx.text(title_x, 635, titre, size=title_size, bold=True, italic=True)
    ctx.line(title_x, 631, title_x + _text_width(titre, title_size, bold=True), 631, width=0.7)

    y = 560
    x = 71
    width = 460
    size = 10.5
    line_height = 15

    y = _draw_paragraph(
        ctx,
        x,
        y,
        [
            (
                (
                    f"Nous soussignés, Société {entreprise.raison_sociale}, {entreprise.nom_commercial}, "
                    f"immatriculée au RC Marrakech sous le numéro {entreprise.rc} domiciliée au {entreprise.adresse}, "
                    f"{ville}, représentée par son gérant M. AMINE ERRARAY."
                ),
                False,
            )
        ],
        width=width,
        size=size,
        line_height=line_height,
        after=18,
    )
    y = _draw_paragraph(
        ctx,
        x,
        y,
        [
            ("Attestons par la présente que le véhicule de marque ", False),
            (f"{vehicule.marque} {vehicule.modele}", True),
            (" immatriculé ", False),
            (vehicule.immatriculation, True),
            (" a été déposé au sein de notre atelier en date du ", False),
            (depot, True),
            (" pour réparation suite à une panne.", False),
        ],
        width=width,
        size=size,
        line_height=line_height,
        after=16,
    )
    y = _draw_paragraph(
        ctx,
        x,
        y,
        [
            ("Le délai de réparation initial estimé est de ", False),
            (f"{_format_jours(jours_reparation)} Jours", True),
            (" à partir de la date de dépôt", False),
        ],
        width=width,
        size=size,
        line_height=line_height,
        after=42,
    )
    _draw_paragraph(
        ctx,
        x,
        y,
        [
            (
                "Cette attestation est délivrée de bonne foi à la demande de l’intéressée pour servir et valoir ce que de droit.",
                False,
            )
        ],
        width=width,
        size=size,
        line_height=line_height,
        after=0,
    )

    fait = _ligne_fait_a(entreprise)
    ctx.text(_center_x(fait, 10.2, bold=True), 350, fait, size=10.2, bold=True)


def _dessiner_pied_attestation(ctx: _PageContext, entreprise) -> None:
    footer_lines = [
        f"RC: {entreprise.rc} / IF: {entreprise.if_fiscal} / ICE: {entreprise.ice} / Patente: {entreprise.patente}",
        f"Adresse: {entreprise.adresse}, {entreprise.ville or 'Marrakech'}",
        f"Tél: {entreprise.telephones} / Email: {entreprise.email}",
    ]
    y = 78
    for line in footer_lines:
        ctx.text(_center_x(line, 10.5, bold=True), y, line, size=10.5, bold=True)
        y -= 17


def _draw_paragraph(
    ctx: _PageContext,
    x: float,
    y: float,
    segments: list[tuple[object, bool]],
    *,
    width: float,
    size: float,
    line_height: float,
    after: float,
) -> float:
    lines = _paragraph_lines(segments, width, size)
    cursor_y = y
    for line in lines:
        if all(not bold for _, bold in line):
            ctx.text(x, cursor_y, " ".join(word for word, _ in line), size=size)
        elif all(bold for _, bold in line):
            ctx.text(x, cursor_y, " ".join(word for word, _ in line), size=size, bold=True)
        else:
            cursor_x = x
            for index, (word, bold) in enumerate(line):
                if index:
                    cursor_x += _text_width(" ", size)
                ctx.text(cursor_x, cursor_y, word, size=size, bold=bold)
                cursor_x += _text_width(word, size, bold=bold)
        cursor_y -= line_height
    return cursor_y - after


def _paragraph_lines(
    segments: list[tuple[object, bool]],
    width: float,
    size: float,
) -> list[list[tuple[str, bool]]]:
    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []
    current_width = 0.0
    space_width = _text_width(" ", size)

    for value, bold in segments:
        for word in str(value or "").split():
            word_width = _text_width(word, size, bold=bold)
            next_width = word_width if not current else current_width + space_width + word_width
            if current and next_width > width:
                lines.append(current)
                current = [(word, bold)]
                current_width = word_width
            else:
                current.append((word, bold))
                current_width = next_width

    if current:
        lines.append(current)
    return lines or [[("-", False)]]


def _center_x(text: str, size: float, *, bold: bool = False) -> float:
    return (_PAGE_WIDTH - _text_width(text, size, bold=bold)) / 2


def _text_width(text: object, size: float, *, bold: bool = False) -> float:
    multiplier = 1.12 if bold else 1
    units = sum(_char_width(char) for char in str(text))
    return units * size * multiplier / 1000


def _char_width(char: str) -> int:
    if char in _HELVETICA_WIDTHS:
        return _HELVETICA_WIDTHS[char]
    normalized = unicodedata.normalize("NFKD", char)
    if normalized and normalized[0] in _HELVETICA_WIDTHS:
        return _HELVETICA_WIDTHS[normalized[0]]
    return 556


def _document_xml_depuis_modele(dossier: DossierReparation, entreprise, jours_reparation: int) -> bytes:
    with ZipFile(_TEMPLATE_PATH, "r") as template:
        root = ET.fromstring(template.read("word/document.xml"))

    paragraphes = _paragraphes_attestation(dossier, entreprise, jours_reparation)
    replacements = (
        ("Nous soussignés", paragraphes[0]),
        ("Attestons par la présente", paragraphes[1]),
        ("Le délai de réparation", paragraphes[2]),
        ("Cette attestation est délivrée", paragraphes[3]),
        ("Fait à", paragraphes[4]),
    )

    for paragraph in root.findall(f".//{{{_W_NS}}}p"):
        text = _texte_paragraphe(paragraph)
        for prefix, replacement in replacements:
            if text.startswith(prefix):
                _remplacer_texte_paragraphe(paragraph, replacement)
                break

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _texte_paragraphe(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph.findall(f".//{{{_W_NS}}}t")).strip()


def _remplacer_texte_paragraphe(paragraph, text: str) -> None:
    ppr = paragraph.find(f"{{{_W_NS}}}pPr")
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    run = ET.SubElement(paragraph, f"{{{_W_NS}}}r")
    text_node = ET.SubElement(run, f"{{{_W_NS}}}t")
    text_node.set(f"{{{_XML_NS}}}space", "preserve")
    text_node.text = text

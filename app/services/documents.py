from pathlib import Path
from uuid import uuid4

from flask import current_app
from flask_login import current_user
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import DocumentDossier, DossierReparation
from app.services.dossiers import RegleMetierErreur, journaliser

EXTENSIONS_AUTORISEES = {"pdf", "png", "jpg", "jpeg", "webp", "xlsx", "docx"}
MIME_AUTORISES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CATEGORIES_DOCUMENTS = {
    "photo_entree",
    "carte_grise",
    "or_sntl",
    "devis_signe",
    "accord_assurance",
    "photo_travaux",
    "bon_livraison",
    "autre",
}
TAILLE_MAX_OCTETS = 12 * 1024 * 1024


def enregistrer_document(
    dossier: DossierReparation,
    fichier: FileStorage,
    categorie: str = "autre",
    description: str = "",
) -> DocumentDossier:
    if not fichier or not fichier.filename:
        raise RegleMetierErreur("Selectionnez un fichier a joindre.")

    nom_original = secure_filename(fichier.filename)
    extension = nom_original.rsplit(".", 1)[-1].lower() if "." in nom_original else ""
    if extension not in EXTENSIONS_AUTORISEES:
        raise RegleMetierErreur("Format de document non autorise.")

    if fichier.mimetype not in MIME_AUTORISES:
        raise RegleMetierErreur("Type de fichier non autorise.")

    fichier.stream.seek(0, 2)
    taille = fichier.stream.tell()
    fichier.stream.seek(0)
    if taille <= 0:
        raise RegleMetierErreur("Le fichier est vide.")
    if taille > TAILLE_MAX_OCTETS:
        raise RegleMetierErreur("Le fichier depasse la taille maximale autorisee de 12 Mo.")

    if extension in {"png", "jpg", "jpeg", "webp"}:
        _verifier_image(fichier)
    elif extension == "pdf":
        _verifier_pdf(fichier)

    categorie = categorie if categorie in CATEGORIES_DOCUMENTS else "autre"
    nom_stockage = f"{uuid4().hex}.{extension}"
    dossier_relatif = Path("uploads") / "dossiers" / str(dossier.id)
    dossier_absolu = Path(current_app.instance_path) / dossier_relatif
    dossier_absolu.mkdir(parents=True, exist_ok=True)
    chemin_absolu = dossier_absolu / nom_stockage
    fichier.save(chemin_absolu)

    document = DocumentDossier(
        dossier_id=dossier.id,
        uploaded_by_id=current_user.id,
        categorie=categorie,
        nom_original=nom_original or f"document.{extension}",
        nom_stockage=nom_stockage,
        chemin_relatif=str(dossier_relatif / nom_stockage),
        mime_type=fichier.mimetype,
        taille_octets=taille,
        description=description.strip(),
    )
    db.session.add(document)
    db.session.flush()
    journaliser(
        dossier,
        "document_ajoute",
        f"Document ajoute : {document.nom_original}.",
        objet_type="document_dossier",
        objet_id=document.id,
        metadonnees={"categorie": categorie, "taille_octets": taille},
    )
    return document


def chemin_document(document: DocumentDossier) -> Path:
    base = Path(current_app.instance_path).resolve()
    chemin = (base / document.chemin_relatif).resolve()
    if not chemin.is_relative_to(base):
        raise RegleMetierErreur("Chemin de document invalide.")
    return chemin


def _verifier_image(fichier: FileStorage) -> None:
    try:
        with Image.open(fichier.stream) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise RegleMetierErreur("Image invalide ou corrompue.") from None
    finally:
        fichier.stream.seek(0)


def _verifier_pdf(fichier: FileStorage) -> None:
    signature = fichier.stream.read(5)
    fichier.stream.seek(0)
    if signature != b"%PDF-":
        raise RegleMetierErreur("PDF invalide ou corrompu.")

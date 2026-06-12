from decimal import Decimal, InvalidOperation
from datetime import date

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models.avance_salaire import AvanceSalaire
from app.models.employe import Employe
from app.models.salaire import Salaire
from app.security import admin_required
from app.services.import_excel import importer_salaires_excel
from app.services.export_salaires import exporter_salaires_excel
from app.services.calcul_salaire import (
    ErreurRH,
    enregistrer_quinzaine,
    enregistrer_solde_fin_mois,
    get_alertes_fin_mois,
    get_jours_ouvrables_quinzaine,
    get_recap_mensuel,
    get_total_mensuel,
)

bp = Blueprint("rh", __name__, url_prefix="/rh")

TYPES_AVANCE_AUTORISES = {"avance", "prime", "tache", "credit", "frais", "cumul", "reste_du"}
FONCTIONS_AUTORISEES = {
    "gerant",
    "chef_atelier",
    "mecanicien",
    "electricien",
    "tolier",
    "peintre",
    "diagnostic",
    "mecanicien_nautique",
    "ouvrier",
    "administratif",
    "autre",
}
TYPES_REMUNERATION_AUTORISES = {"salaire_fixe", "mensuelle", "tache", "mixte"}


# ---------------------------------------------------------------------------
# Vue mensuelle
# ---------------------------------------------------------------------------

@bp.route("/salaires/")
@bp.route("/salaires/<int:annee>/<int:mois>")
@admin_required
def vue_mensuelle(annee: int | None = None, mois: int | None = None):
    aujourd_hui = date.today()
    if annee is None:
        annee = aujourd_hui.year
    if mois is None:
        mois = aujourd_hui.month

    lignes = get_recap_mensuel(mois, annee)
    alertes = get_alertes_fin_mois(mois, annee)
    total = get_total_mensuel(mois, annee)

    return render_template(
        "rh/vue_mensuelle.html",
        lignes=lignes,
        alertes=alertes,
        total=total,
        mois=mois,
        annee=annee,
        mois_precedent=_mois_precedent(mois, annee),
        mois_suivant=_mois_suivant(mois, annee),
        mois_courant=(mois == aujourd_hui.month and annee == aujourd_hui.year),
        jours_ouvrables_fin_mois=get_jours_ouvrables_quinzaine(mois, annee, 2),
    )


@bp.route("/salaires/<int:annee>/<int:mois>/payer-quinzaine", methods=["POST"])
@admin_required
def payer_quinzaine(annee: int, mois: int):
    employes = Employe.query.filter(
        Employe.actif == True,
        Employe.type_remuneration.in_(["salaire_fixe", "mixte"]),
    ).all()

    payes, ignores, erreurs = 0, 0, []
    for emp in employes:
        try:
            enregistrer_quinzaine(emp, mois, annee)
            payes += 1
        except ErreurRH:
            ignores += 1
        except Exception as e:
            erreurs.append(f"{emp.nom_complet}: {e}")

    db.session.commit()

    if payes:
        flash(f"Quinzaine enregistrée pour {payes} employé(s).", "success")
    if ignores:
        flash(f"{ignores} quinzaine(s) déjà enregistrée(s), ignorée(s).", "info")
    for msg in erreurs:
        flash(msg, "danger")

    return redirect(url_for("rh.vue_mensuelle", annee=annee, mois=mois))


@bp.route("/salaires/<int:annee>/<int:mois>/calculer-soldes", methods=["POST"])
@admin_required
def calculer_soldes(annee: int, mois: int):
    employes = Employe.query.filter(
        Employe.actif == True,
        Employe.type_remuneration.in_(["salaire_fixe", "mixte", "mensuelle"]),
    ).all()

    # Jours travaillés transmis par formulaire (optionnel, pour prorata)
    payes, ignores, erreurs = 0, 0, []
    for emp in employes:
        jours_str = request.form.get(f"jours_{emp.id}", "").strip()
        jours = int(jours_str) if jours_str.isdigit() else None
        brut_solde = _decimal_ou_none(request.form.get(f"brut_solde_{emp.id}"))
        try:
            enregistrer_solde_fin_mois(emp, mois, annee, jours_travailles=jours, brut_solde=brut_solde)
            payes += 1
        except ErreurRH:
            ignores += 1
        except Exception as e:
            erreurs.append(f"{emp.nom_complet}: {e}")

    db.session.commit()

    if payes:
        flash(f"Soldes fin de mois calculés pour {payes} employé(s).", "success")
    if ignores:
        flash(f"{ignores} solde(s) déjà enregistré(s), ignoré(s).", "info")
    for msg in erreurs:
        flash(msg, "danger")

    return redirect(url_for("rh.vue_mensuelle", annee=annee, mois=mois))


@bp.route("/employes/<int:employe_id>/payer-quinzaine", methods=["POST"])
@admin_required
def payer_quinzaine_employe(employe_id: int):
    employe = db.session.get(Employe, employe_id)
    mois = _int_ou_none(request.form.get("mois")) or date.today().month
    annee = _int_ou_none(request.form.get("annee")) or date.today().year

    if not employe:
        flash("Employé introuvable.", "warning")
        return redirect(url_for("rh.liste_employes"))

    try:
        enregistrer_quinzaine(employe, mois, annee)
        db.session.commit()
        flash(f"Quinzaine enregistrée pour {employe.nom_complet}.", "success")
    except ErreurRH as exc:
        db.session.rollback()
        flash(str(exc), "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur lors de la quinzaine : {exc}", "danger")

    return redirect(url_for("rh.fiche_employe", employe_id=employe.id, mois=mois, annee=annee))


@bp.route("/employes/<int:employe_id>/calculer-solde", methods=["POST"])
@admin_required
def calculer_solde_employe(employe_id: int):
    employe = db.session.get(Employe, employe_id)
    mois = _int_ou_none(request.form.get("mois")) or date.today().month
    annee = _int_ou_none(request.form.get("annee")) or date.today().year

    if not employe:
        flash("Employé introuvable.", "warning")
        return redirect(url_for("rh.liste_employes"))

    jours_str = request.form.get("jours_travailles", "").strip()
    jours = int(jours_str) if jours_str.isdigit() else None
    brut_solde = _decimal_ou_none(request.form.get("brut_solde"))

    try:
        enregistrer_solde_fin_mois(
            employe,
            mois,
            annee,
            jours_travailles=jours,
            brut_solde=brut_solde,
        )
        db.session.commit()
        flash(f"Solde fin de mois calculé pour {employe.nom_complet}.", "success")
    except ErreurRH as exc:
        db.session.rollback()
        flash(str(exc), "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erreur lors du solde : {exc}", "danger")

    return redirect(url_for("rh.fiche_employe", employe_id=employe.id, mois=mois, annee=annee))


# ---------------------------------------------------------------------------
# Avances & primes
# ---------------------------------------------------------------------------

@bp.route("/avances/nouvelle", methods=["POST"])
@admin_required
def nouvelle_avance():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def err(msg):
        if is_ajax:
            return jsonify({"ok": False, "message": msg}), 400
        flash(msg, "danger")
        return _redirect_retour()

    employe_id = _int_ou_none(request.form.get("employe_id"))
    if not employe_id:
        return err("Employé obligatoire.")

    employe = db.session.get(Employe, employe_id)
    if not employe:
        return err("Employé introuvable.")

    montant_str = request.form.get("montant", "").strip().replace(",", ".")
    try:
        montant = Decimal(montant_str)
        if montant <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return err("Montant invalide.")

    type_avance = request.form.get("type", "avance")
    if type_avance not in TYPES_AVANCE_AUTORISES:
        return err("Type d'opération invalide.")

    date_str = request.form.get("date", "").strip()
    try:
        date_op = date.fromisoformat(date_str)
    except ValueError:
        return err("Date invalide.")

    quinzaine = "premiere" if date_op.day <= 15 else "seconde"

    avance = AvanceSalaire(
        employe_id=employe_id,
        date=date_op,
        montant=montant,
        type=type_avance,
        description=request.form.get("description", "").strip(),
        vehicule_id=_int_ou_none(request.form.get("vehicule_id")),
        quinzaine=quinzaine,
        mois=date_op.month,
        annee=date_op.year,
        montant_total_convenu=_float_ou_none(request.form.get("montant_total_convenu")),
        reste_du=_float_ou_none(request.form.get("reste_du")),
    )
    db.session.add(avance)
    db.session.commit()

    msg = f"{avance.type_libelle} de {montant:,.2f} DH enregistrée pour {employe.nom_complet}."
    if is_ajax:
        return jsonify({"ok": True, "message": msg})
    flash(msg, "success")
    return _redirect_retour()


@bp.route("/avances/<int:avance_id>/supprimer", methods=["POST"])
@admin_required
def supprimer_avance(avance_id: int):
    avance = db.session.get(AvanceSalaire, avance_id)
    if not avance:
        flash("Opération introuvable.", "warning")
        return _redirect_retour()

    nom = avance.employe.nom_complet
    mois, annee = avance.mois, avance.annee
    db.session.delete(avance)
    db.session.commit()
    flash(f"Opération supprimée ({nom}).", "success")
    return redirect(url_for("rh.vue_mensuelle", annee=annee, mois=mois))


# ---------------------------------------------------------------------------
# Export Excel
# ---------------------------------------------------------------------------

@bp.route("/salaires/<int:annee>/<int:mois>/telecharger")
@admin_required
def export_xlsx(annee: int, mois: int):
    if not (1 <= mois <= 12 and annee >= 2020):
        flash("Période invalide.", "danger")
        return redirect(url_for("rh.vue_mensuelle"))

    try:
        data = exporter_salaires_excel(mois, annee)
    except Exception as exc:
        flash(f"Erreur lors de l'export : {exc}", "danger")
        return redirect(url_for("rh.vue_mensuelle", annee=annee, mois=mois))

    filename = f"SALAIRES_{annee}_{mois:02d}.xlsx"
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Import Excel
# ---------------------------------------------------------------------------

@bp.route("/import-excel", methods=["GET", "POST"])
@admin_required
def import_excel():
    if request.method == "GET":
        aujourd_hui = date.today()
        return render_template(
            "rh/import_excel.html",
            today_mois=aujourd_hui.month,
            today_annee=aujourd_hui.year,
        )

    fichier = request.files.get("fichier")
    mois = _int_ou_none(request.form.get("mois"))
    annee = _int_ou_none(request.form.get("annee"))

    if not fichier or not fichier.filename:
        flash("Aucun fichier sélectionné.", "danger")
        return render_template("rh/import_excel.html")

    if not (mois and annee and 1 <= mois <= 12 and annee >= 2020):
        flash("Mois et année invalides.", "danger")
        return render_template("rh/import_excel.html")

    if not fichier.filename.lower().endswith(".xlsx"):
        flash("Format invalide — fichier .xlsx uniquement.", "danger")
        return render_template("rh/import_excel.html")

    try:
        resultat = importer_salaires_excel(fichier.stream, mois=mois, annee=annee)
    except ValueError as exc:
        flash(str(exc), "danger")
        return render_template("rh/import_excel.html")
    except Exception as exc:
        flash(f"Erreur lors de l'import : {exc}", "danger")
        return render_template("rh/import_excel.html")

    return render_template(
        "rh/import_resultat.html",
        resultat=resultat,
        mois=mois,
        annee=annee,
    )


# ---------------------------------------------------------------------------
# Employés
# ---------------------------------------------------------------------------

@bp.route("/employes/")
@admin_required
def liste_employes():
    employes = Employe.query.order_by(Employe.actif.desc(), Employe.nom_complet).all()
    return render_template("rh/employes.html", employes=employes)


@bp.route("/employes/nouveau", methods=["GET", "POST"])
@admin_required
def nouvel_employe():
    if request.method == "POST":
        nom = request.form.get("nom_complet", "").strip().upper()
        if not nom:
            flash("Le nom est obligatoire.", "danger")
            return render_template("rh/formulaire_employe.html", employe=None)

        fonction = request.form.get("fonction", "ouvrier")
        if fonction not in FONCTIONS_AUTORISEES:
            flash("Fonction invalide.", "danger")
            return render_template("rh/formulaire_employe.html", employe=None)

        type_remuneration = request.form.get("type_remuneration", "tache")
        if type_remuneration not in TYPES_REMUNERATION_AUTORISES:
            flash("Type de rémunération invalide.", "danger")
            return render_template("rh/formulaire_employe.html", employe=None)

        salaire_q = _float_ou_none(request.form.get("salaire_quinzaine"))
        salaire_m = _float_ou_none(request.form.get("salaire_mensuel"))
        if type_remuneration in ("salaire_fixe", "mixte") and not salaire_q:
            flash("Le salaire quinzaine est obligatoire pour un employé à salaire fixe.", "danger")
            return render_template("rh/formulaire_employe.html", employe=None)
        if type_remuneration == "mensuelle" and not salaire_m:
            flash("Le salaire mensuel est obligatoire pour un employé mensuel.", "danger")
            return render_template("rh/formulaire_employe.html", employe=None)

        employe = Employe(
            nom_complet=nom,
            cin=request.form.get("cin", "").strip().upper() or None,
            fonction=fonction,
            telephone=request.form.get("telephone", "").strip() or None,
            adresse=request.form.get("adresse", "").strip() or None,
            date_embauche=_date_ou_none(request.form.get("date_embauche")),
            type_remuneration=type_remuneration,
            salaire_quinzaine=salaire_q,
            salaire_mensuel=salaire_m,
        )
        db.session.add(employe)
        db.session.commit()
        flash(f"Employé {employe.nom_complet} enregistré.", "success")
        return redirect(url_for("rh.fiche_employe", employe_id=employe.id))

    return render_template("rh/formulaire_employe.html", employe=None)


@bp.route("/employes/<int:employe_id>")
@admin_required
def fiche_employe(employe_id: int):
    employe = db.session.get(Employe, employe_id)
    if not employe:
        flash("Employé introuvable.", "warning")
        return redirect(url_for("rh.liste_employes"))

    mois = _int_ou_none(request.args.get("mois")) or date.today().month
    annee = _int_ou_none(request.args.get("annee")) or date.today().year

    avances = (
        AvanceSalaire.query
        .filter_by(employe_id=employe_id, mois=mois, annee=annee)
        .order_by(AvanceSalaire.date)
        .all()
    )
    salaires = (
        Salaire.query
        .filter_by(employe_id=employe_id, mois=mois, annee=annee)
        .order_by(Salaire.date)
        .all()
    )
    quinzaine_rec = next((s for s in salaires if s.type_paie == "quinzaine"), None)
    solde_rec = next((s for s in salaires if s.type_paie == "fin_mois"), None)

    return render_template(
        "rh/fiche_employe.html",
        employe=employe,
        avances=avances,
        salaires=salaires,
        quinzaine_rec=quinzaine_rec,
        solde_rec=solde_rec,
        mois=mois,
        annee=annee,
        jours_ouvrables_fin_mois=get_jours_ouvrables_quinzaine(mois, annee, 2),
    )


@bp.route("/employes/<int:employe_id>/modifier", methods=["GET", "POST"])
@admin_required
def modifier_employe(employe_id: int):
    employe = db.session.get(Employe, employe_id)
    if not employe:
        flash("Employé introuvable.", "warning")
        return redirect(url_for("rh.liste_employes"))

    if request.method == "POST":
        nom = request.form.get("nom_complet", "").strip().upper()
        if not nom:
            flash("Le nom est obligatoire.", "danger")
            return render_template("rh/formulaire_employe.html", employe=employe)

        fonction = request.form.get("fonction", employe.fonction)
        if fonction not in FONCTIONS_AUTORISEES:
            flash("Fonction invalide.", "danger")
            return render_template("rh/formulaire_employe.html", employe=employe)

        type_remuneration = request.form.get("type_remuneration", employe.type_remuneration)
        if type_remuneration not in TYPES_REMUNERATION_AUTORISES:
            flash("Type de rémunération invalide.", "danger")
            return render_template("rh/formulaire_employe.html", employe=employe)

        salaire_q = _float_ou_none(request.form.get("salaire_quinzaine"))
        salaire_m = _float_ou_none(request.form.get("salaire_mensuel"))
        if type_remuneration in ("salaire_fixe", "mixte") and not salaire_q:
            flash("Le salaire quinzaine est obligatoire pour un employé à salaire fixe.", "danger")
            return render_template("rh/formulaire_employe.html", employe=employe)
        if type_remuneration == "mensuelle" and not salaire_m:
            flash("Le salaire mensuel est obligatoire pour un employé mensuel.", "danger")
            return render_template("rh/formulaire_employe.html", employe=employe)

        employe.nom_complet = nom
        employe.cin = request.form.get("cin", "").strip().upper() or None
        employe.fonction = fonction
        employe.telephone = request.form.get("telephone", "").strip() or None
        employe.adresse = request.form.get("adresse", "").strip() or None
        employe.date_embauche = _date_ou_none(request.form.get("date_embauche"))
        employe.type_remuneration = type_remuneration
        employe.salaire_quinzaine = salaire_q
        employe.salaire_mensuel = salaire_m
        employe.actif = request.form.get("actif") == "1"

        db.session.commit()
        flash("Fiche employé mise à jour.", "success")
        return redirect(url_for("rh.fiche_employe", employe_id=employe.id))

    return render_template("rh/formulaire_employe.html", employe=employe)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mois_precedent(mois: int, annee: int) -> tuple[int, int]:
    if mois == 1:
        return (12, annee - 1)
    return (mois - 1, annee)


def _mois_suivant(mois: int, annee: int) -> tuple[int, int]:
    if mois == 12:
        return (1, annee + 1)
    return (mois + 1, annee)


def _redirect_retour():
    retour = request.form.get("retour") or request.referrer
    if retour:
        return redirect(retour)
    return redirect(url_for("rh.vue_mensuelle"))


def _int_ou_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float_ou_none(val):
    if not val:
        return None


def _decimal_ou_none(val):
    if not val:
        return None
    try:
        return Decimal(str(val).replace(",", "."))
    except InvalidOperation:
        return None
    try:
        return float(str(val).replace(",", "."))
    except ValueError:
        return None


def _date_ou_none(val):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None

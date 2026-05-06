from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models import ParametreSysteme
from app.security import admin_required
from app.services.parametres import assurer_parametres_defaut, obtenir_entreprise

bp = Blueprint("parametres", __name__, url_prefix="/parametres")


@bp.route("/")
@admin_required
def index():
    return redirect(url_for("parametres.entreprise"))


@bp.route("/entreprise", methods=["GET", "POST"])
@admin_required
def entreprise():
    entreprise = obtenir_entreprise()

    if request.method == "POST":
        champs = [
            "raison_sociale",
            "nom_commercial",
            "adresse",
            "ville",
            "telephones",
            "email",
            "rc",
            "if_fiscal",
            "ice",
            "patente",
            "cnss",
            "rib",
            "agrement_sntl",
        ]

        for champ in champs:
            setattr(entreprise, champ, request.form.get(champ, "").strip())

        if not entreprise.raison_sociale or not entreprise.adresse:
            flash("La raison sociale et l'adresse sont obligatoires.", "danger")
            return render_template("parametres/entreprise.html", entreprise=entreprise)

        db.session.commit()
        flash("Informations de l'entreprise enregistrées.", "success")
        return redirect(url_for("parametres.entreprise"))

    return render_template("parametres/entreprise.html", entreprise=entreprise)


@bp.route("/systeme", methods=["GET", "POST"])
@admin_required
def systeme():
    assurer_parametres_defaut()
    parametres = ParametreSysteme.query.order_by(ParametreSysteme.cle.asc()).all()

    if request.method == "POST":
        for parametre in parametres:
            parametre.valeur = request.form.get(parametre.cle, "").strip()

        db.session.commit()
        flash("Paramètres système enregistrés.", "success")
        return redirect(url_for("parametres.systeme"))

    return render_template("parametres/systeme.html", parametres=parametres)


from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, login_manager
from app.models import Utilisateur

bp = Blueprint("auth", __name__, url_prefix="/auth")


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(Utilisateur, int(user_id))


@bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.accueil"))

    if request.method == "POST":
        login = request.form.get("login", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")
        utilisateur = Utilisateur.query.filter_by(login=login).first()

        if utilisateur and utilisateur.verifier_mot_de_passe(mot_de_passe) and utilisateur.actif:
            utilisateur.derniere_connexion = datetime.now(timezone.utc)
            db.session.commit()
            login_user(utilisateur)
            session.permanent = True
            session["derniere_activite"] = datetime.now(timezone.utc).isoformat()
            flash("Connexion réussie.", "success")
            return redirect(request.args.get("next") or url_for("dashboard.accueil"))

        flash("Identifiant ou mot de passe incorrect.", "danger")

    return render_template("auth/connexion.html")


@bp.route("/deconnexion", methods=["POST"])
@login_required
def deconnexion():
    logout_user()
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("auth.connexion"))

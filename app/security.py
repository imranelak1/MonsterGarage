from datetime import datetime, timezone
from functools import wraps

from flask import current_app, flash, redirect, request, session, url_for
from flask_login import current_user, logout_user


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.connexion", next=request.url))

        if not current_user.est_admin:
            flash("Accès réservé au gérant.", "warning")
            return redirect(url_for("dashboard.accueil"))

        return view_func(*args, **kwargs)

    return wrapped_view


def register_session_timeout(app):
    @app.before_request
    def verifier_expiration_session():
        if request.endpoint == "static" or not current_user.is_authenticated:
            return None

        maintenant = datetime.now(timezone.utc)
        derniere_activite = session.get("derniere_activite")

        if derniere_activite:
            derniere_activite = datetime.fromisoformat(derniere_activite)
            duree_inactivite = maintenant - derniere_activite
            if duree_inactivite > current_app.permanent_session_lifetime:
                logout_user()
                session.clear()
                flash("Session expirée. Veuillez vous reconnecter.", "warning")
                return redirect(url_for("auth.connexion"))

        session["derniere_activite"] = maintenant.isoformat()
        return None

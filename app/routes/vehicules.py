from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from app.models import Client, Vehicule

bp = Blueprint("vehicules", __name__, url_prefix="/vehicules")


@bp.route("/")
@login_required
def liste():
    recherche = request.args.get("q", "").strip()
    requete = Vehicule.query.join(Client)

    if recherche:
        motif = f"%{recherche}%"
        requete = requete.filter(
            or_(
                Vehicule.immatriculation.ilike(motif),
                Vehicule.marque.ilike(motif),
                Vehicule.modele.ilike(motif),
                Vehicule.vin.ilike(motif),
                Client.nom.ilike(motif),
            )
        )

    vehicules = requete.order_by(Vehicule.created_at.desc()).limit(100).all()
    return render_template("vehicules/liste.html", vehicules=vehicules, recherche=recherche)

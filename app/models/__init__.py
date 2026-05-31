from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.extensions import db

_sqlite_pragmas_registered = False


def register_sqlite_pragmas() -> None:
    global _sqlite_pragmas_registered
    if _sqlite_pragmas_registered:
        return

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    _sqlite_pragmas_registered = True


from app.models.entreprise import Entreprise
from app.models.parametre import ParametreSysteme
from app.models.utilisateur import Utilisateur
from app.models.client import Client
from app.models.vehicule import Vehicule
from app.models.dossier_reparation import DossierReparation, JournalAction
from app.models.devis_reparation import DevisReparation, LigneDevisReparation
from app.models.facture_reparation import FactureReparation
from app.models.chiffre_affaires import EntreeChiffreAffaires
from app.models.employe import Employe
from app.models.avance_salaire import AvanceSalaire
from app.models.salaire import Salaire

__all__ = [
    "AvanceSalaire",
    "Client",
    "DevisReparation",
    "DossierReparation",
    "Employe",
    "EntreeChiffreAffaires",
    "Entreprise",
    "FactureReparation",
    "JournalAction",
    "LigneDevisReparation",
    "ParametreSysteme",
    "Salaire",
    "Utilisateur",
    "Vehicule",
    "db",
]

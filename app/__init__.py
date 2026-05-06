from flask import Flask

from app.config import config_by_name
from app.extensions import db, login_manager, migrate
from app.models import register_sqlite_pragmas
from app.security import register_session_timeout


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.connexion"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    register_sqlite_pragmas()
    register_blueprints(app)
    register_session_timeout(app)

    return app


def register_blueprints(app: Flask) -> None:
    from app.routes.auth import bp as auth_bp
    from app.routes.clients import bp as clients_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.dossiers import bp as dossiers_bp
    from app.routes.factures import bp as factures_bp
    from app.routes.parametres import bp as parametres_bp
    from app.routes.rh import bp as rh_bp
    from app.routes.vehicules import bp as vehicules_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(dossiers_bp)
    app.register_blueprint(factures_bp)
    app.register_blueprint(parametres_bp)
    app.register_blueprint(rh_bp)
    app.register_blueprint(vehicules_bp)

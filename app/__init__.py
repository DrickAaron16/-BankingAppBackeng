from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import os

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object("config.Config")

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)
    CORS(app)

    # Créer le dossier uploads si nécessaire
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Enregistrer les blueprints
    from app.auth import auth_bp
    from app.api.accounts import accounts_bp
    from app.api.transactions import transactions_bp
    from app.api.cheques import cheques_bp
    from app.api.cheques_emis import cheques_emis_bp
    from app.api.remises import remises_bp
    from app.api.chef_caisse import chef_caisse_bp
    from app.web.caissier import caissier_bp
    from app.web.gestionnaire import gestionnaire_bp
    from app.web.chef_caisse import chef_caisse_bp as chef_caisse_web_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(accounts_bp, url_prefix="/api/accounts")
    app.register_blueprint(transactions_bp, url_prefix="/api/transactions")
    app.register_blueprint(cheques_bp, url_prefix="/api/cheques")
    app.register_blueprint(cheques_emis_bp, url_prefix="/api/cheques-emis")
    app.register_blueprint(remises_bp, url_prefix="/api/remises")
    app.register_blueprint(chef_caisse_bp, url_prefix="/api/chef-caisse")
    app.register_blueprint(caissier_bp, url_prefix="/caissier")
    app.register_blueprint(gestionnaire_bp, url_prefix="/gestionnaire")
    app.register_blueprint(chef_caisse_web_bp, url_prefix="/chef-caisse")

    return app

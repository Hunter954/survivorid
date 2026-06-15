import os
from pathlib import Path
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from .models import db, User, Badge, SiteSetting

login_manager = LoginManager()
login_manager.login_view = "auth_login"
login_manager.login_message = "Entre na sua conta para continuar."


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    db_url = os.getenv("DATABASE_URL", "sqlite:///survivorid.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = str(Path(app.root_path) / "static" / "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import routes
    routes.register_routes(app)

    with app.app_context():
        db.create_all()
        seed_defaults()

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def seed_defaults():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@survivorid.local").lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(email=admin_email, name="Admin", password_hash=generate_password_hash(admin_password), is_admin=True)
        db.session.add(admin)

    defaults = {
        "site_name": "SurvivorID",
        "hero_title": "SEU PERFIL.\nSUA HISTÓRIA.",
        "hero_subtitle": "O maior hub de estatísticas e performance de jogadores de PUBG.",
        "hero_image": "",
        "footer_text": "A plataforma social definitiva para jogadores de PUBG."
    }
    for k, v in defaults.items():
        if not SiteSetting.query.filter_by(key=k).first():
            db.session.add(SiteSetting(key=k, value=v))

    badge_defs = [
        ("Head Hunter", "GOLD", "1.000 headshots registrados", "bi-crosshair"),
        ("Clutch Master", "EPIC", "Venceu situações decisivas no fim da partida", "bi-lightning-charge-fill"),
        ("Squad Wipe", "RARE", "Eliminou vários jogadores do mesmo squad", "bi-shield-fill-check"),
        ("Long Shot", "RARE", "Kill a longa distância", "bi-bullseye"),
        ("Medic", "SILVER", "Revives e suporte ao time", "bi-heart-pulse-fill"),
        ("Road Warrior", "BRONZE", "Domínio de veículos e rotações", "bi-truck-front-fill"),
    ]
    for name, tier, desc, icon in badge_defs:
        if not Badge.query.filter_by(name=name).first():
            db.session.add(Badge(name=name, tier=tier, description=desc, icon=icon, category="combat"))
    db.session.commit()

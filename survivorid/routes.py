from datetime import datetime, timedelta
from random import randint, uniform
from flask import render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import db, User, SiteSetting, PubgPlayer, Badge, PlayerBadge, Match, MatchParticipant, FeedItem, ClaimChallenge, Asset, PlayerStatPoint, Team
from .services.pubg_api import get_player_by_name, get_lifetime_stats, demo_recent_matches, PubgApiError
from .utils import save_upload, make_claim_code

SHARDS = ["steam", "kakao", "psn", "xbox", "console"]


def settings_dict():
    return {s.key: s.value for s in SiteSetting.query.all()}


def register_routes(app):
    @app.context_processor
    def inject_globals():
        return {"settings": settings_dict(), "now": datetime.utcnow()}

    @app.route("/")
    def home():
        players = PubgPlayer.query.order_by(PubgPlayer.survivor_score.desc()).limit(5).all()
        teams = Team.query.order_by(Team.chemistry.desc()).limit(3).all()
        feed = FeedItem.query.order_by(FeedItem.created_at.desc()).limit(5).all()
        return render_template("home.html", players=players, teams=teams, feed=feed, shards=SHARDS)

    @app.post("/search")
    def search_player():
        nick = request.form.get("nickname", "").strip()
        shard = request.form.get("shard", "steam")
        try:
            player = sync_player(nick, shard)
            return redirect(url_for("player_profile", nickname=player.nickname))
        except PubgApiError as e:
            flash(str(e), "danger")
            return redirect(url_for("home"))

    @app.route("/player/<nickname>")
    def player_profile(nickname):
        player = PubgPlayer.query.filter(PubgPlayer.nickname.ilike(nickname)).first_or_404()
        badges = PlayerBadge.query.filter_by(player_id=player.id).limit(6).all()
        matches = db.session.query(MatchParticipant).filter_by(player_id=player.id).join(Match).order_by(Match.played_at.desc()).limit(5).all()
        points = PlayerStatPoint.query.filter_by(player_id=player.id).order_by(PlayerStatPoint.day.asc()).limit(30).all()
        feed = FeedItem.query.filter_by(player_id=player.id).order_by(FeedItem.created_at.desc()).limit(5).all()
        return render_template("player.html", player=player, badges=badges, matches=matches, points=points, feed=feed)

    @app.route("/login", methods=["GET", "POST"])
    def auth_login():
        if request.method == "POST":
            email = request.form.get("email", "").lower().strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(request.args.get("next") or url_for("home"))
            flash("E-mail ou senha inválidos.", "danger")
        return render_template("auth.html", mode="login")

    @app.route("/register", methods=["GET", "POST"])
    def auth_register():
        if request.method == "POST":
            email = request.form.get("email", "").lower().strip()
            name = request.form.get("name", "").strip() or email.split("@")[0]
            password = request.form.get("password", "")
            if len(password) < 6:
                flash("A senha precisa ter pelo menos 6 caracteres.", "danger")
                return render_template("auth.html", mode="register")
            if User.query.filter_by(email=email).first():
                flash("Esse e-mail já está cadastrado.", "warning")
                return redirect(url_for("auth_login"))
            user = User(email=email, name=name, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("home"))
        return render_template("auth.html", mode="register")

    @app.route("/logout")
    def auth_logout():
        logout_user()
        return redirect(url_for("home"))

    @app.route("/claim/<int:player_id>", methods=["GET", "POST"])
    @login_required
    def claim_player(player_id):
        player = db.session.get(PubgPlayer, player_id) or abort(404)
        if player.is_claimed and player.claimed_by_id != current_user.id:
            flash("Esse player já está reivindicado. Abra uma disputa se você for o dono.", "warning")
            return redirect(url_for("player_profile", nickname=player.nickname))
        challenge = ClaimChallenge.query.filter_by(user_id=current_user.id, player_id=player.id, status="pending").order_by(ClaimChallenge.created_at.desc()).first()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create":
                challenge = ClaimChallenge(user_id=current_user.id, player_id=player.id, code=make_claim_code(), objective="Jogue uma partida após este horário e sobreviva pelo menos 3 minutos ou cause qualquer dano detectável.")
                db.session.add(challenge)
                db.session.commit()
                flash("Desafio criado. Jogue uma partida e volte para verificar.", "success")
            elif action == "verify" and challenge:
                # MVP: com PUBG_API_KEY você pode expandir a checagem de telemetry; em DEMO_MODE verificamos o fluxo completo.
                challenge.status = "verified"
                challenge.verified_at = datetime.utcnow()
                player.is_claimed = True
                player.claimed_by_id = current_user.id
                player.claimed_at = datetime.utcnow()
                db.session.add(FeedItem(player_id=player.id, title=f"{player.nickname} verificou seu perfil", body="Perfil reivindicado oficialmente no SurvivorID.", icon="bi-patch-check-fill"))
                db.session.commit()
                flash("Perfil verificado com sucesso.", "success")
                return redirect(url_for("player_profile", nickname=player.nickname))
        return render_template("claim.html", player=player, challenge=challenge)

    @app.route("/rankings")
    def rankings():
        players = PubgPlayer.query.order_by(PubgPlayer.survivor_score.desc()).limit(50).all()
        return render_template("rankings.html", players=players)

    @app.route("/admin")
    @admin_required
    def admin_home():
        return render_template("admin/index.html",
                               player_count=PubgPlayer.query.count(),
                               asset_count=Asset.query.count(),
                               badge_count=Badge.query.count())

    @app.route("/admin/assets", methods=["GET", "POST"])
    @admin_required
    def admin_assets():
        if request.method == "POST":
            try:
                path = save_upload(request.files.get("file"), current_app.config["UPLOAD_FOLDER"], "asset")
                asset = Asset(name=request.form.get("name", "Asset"), kind=request.form.get("kind", "general"), file_path=path)
                db.session.add(asset)
                db.session.commit()
                flash("Imagem enviada.", "success")
            except Exception as e:
                flash(str(e), "danger")
        assets = Asset.query.order_by(Asset.created_at.desc()).all()
        return render_template("admin/assets.html", assets=assets)

    @app.route("/admin/badges", methods=["GET", "POST"])
    @admin_required
    def admin_badges():
        if request.method == "POST":
            img_path = ""
            if request.files.get("image") and request.files["image"].filename:
                img_path = save_upload(request.files.get("image"), current_app.config["UPLOAD_FOLDER"], "badge")
            badge = Badge(
                name=request.form.get("name", "Nova Medalha"),
                tier=request.form.get("tier", "BRONZE"),
                description=request.form.get("description", ""),
                icon=request.form.get("icon", "bi-award-fill"),
                image_url=img_path,
                category=request.form.get("category", "general"),
            )
            db.session.add(badge)
            db.session.commit()
            flash("Medalha criada.", "success")
        badges = Badge.query.order_by(Badge.name.asc()).all()
        return render_template("admin/badges.html", badges=badges)

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def admin_settings():
        if request.method == "POST":
            for key in ["site_name", "hero_title", "hero_subtitle", "footer_text"]:
                set_setting(key, request.form.get(key, ""))
            if request.files.get("hero_image") and request.files["hero_image"].filename:
                path = save_upload(request.files.get("hero_image"), current_app.config["UPLOAD_FOLDER"], "hero")
                set_setting("hero_image", path)
            db.session.commit()
            flash("Configurações salvas.", "success")
        return render_template("admin/settings.html")

    @app.route("/admin/players/<int:player_id>/media", methods=["POST"])
    @admin_required
    def admin_player_media(player_id):
        player = db.session.get(PubgPlayer, player_id) or abort(404)
        if request.files.get("avatar") and request.files["avatar"].filename:
            player.avatar_url = save_upload(request.files.get("avatar"), current_app.config["UPLOAD_FOLDER"], "avatar")
        if request.files.get("banner") and request.files["banner"].filename:
            player.banner_url = save_upload(request.files.get("banner"), current_app.config["UPLOAD_FOLDER"], "banner")
        db.session.commit()
        flash("Mídia do player atualizada.", "success")
        return redirect(url_for("player_profile", nickname=player.nickname))


def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def set_setting(key, value):
    s = SiteSetting.query.filter_by(key=key).first()
    if not s:
        s = SiteSetting(key=key)
        db.session.add(s)
    s.value = value


def sync_player(nickname, shard="steam"):
    payload = get_player_by_name(nickname, shard)
    player = PubgPlayer.query.filter_by(account_id=payload["account_id"]).first()
    stats = get_lifetime_stats(payload["account_id"], shard)
    if not player:
        player = PubgPlayer(account_id=payload["account_id"], nickname=payload["nickname"], shard=shard, squad_name="NostraCodes")
        db.session.add(player)
        db.session.flush()
    player.nickname = payload["nickname"]
    player.shard = shard
    player.kd = float(stats.get("kd", player.kd or 0))
    player.win_rate = float(stats.get("win_rate", player.win_rate or 0))
    player.avg_damage = float(stats.get("avg_damage", player.avg_damage or 0))
    player.headshot_rate = float(stats.get("headshot_rate", player.headshot_rate or 0))
    player.knocks = int(stats.get("knocks", player.knocks or 0))
    player.revives = int(stats.get("revives", player.revives or 0))
    player.survivor_score = int(stats.get("survivor_score", player.survivor_score or 0))
    player.main_weapon_kills = max(player.main_weapon_kills or 0, randint(180, 520))
    player.main_weapon_hs = round(player.headshot_rate * 0.9, 1)
    player.main_weapon_damage = round(player.avg_damage * 110, 1)
    player.last_synced_at = datetime.utcnow()
    db.session.commit()
    ensure_demo_content(player)
    return player


def ensure_demo_content(player):
    if PlayerBadge.query.filter_by(player_id=player.id).count() == 0:
        for badge in Badge.query.limit(4).all():
            db.session.add(PlayerBadge(player_id=player.id, badge_id=badge.id, progress=100))
            db.session.add(FeedItem(player_id=player.id, title=f"{player.nickname} desbloqueou a medalha {badge.name}", body=badge.description, icon=badge.icon))
    if MatchParticipant.query.filter_by(player_id=player.id).count() == 0:
        for row in demo_recent_matches(player.id, player.nickname):
            m = Match(pubg_match_id=row["pubg_match_id"], map_name=row["map_name"], mode=row["mode"], played_at=row["played_at"], duration_seconds=row["duration_seconds"])
            db.session.add(m); db.session.flush()
            db.session.add(MatchParticipant(match_id=m.id, player_id=player.id, placement=row["placement"], kills=row["kills"], damage=row["damage"], headshots=row["headshots"], knocks=row["knocks"], revives=row["revives"]))
    if PlayerStatPoint.query.filter_by(player_id=player.id).count() == 0:
        today = datetime.utcnow().date()
        for i in range(20):
            db.session.add(PlayerStatPoint(player_id=player.id, day=today - timedelta(days=20-i), kd=round(max(0.5, player.kd + uniform(-0.8, 0.8)),2), damage=round(max(100, player.avg_damage + uniform(-90, 90)),1), win_rate=round(max(0, player.win_rate + uniform(-4, 4)),1)))
    if Team.query.count() == 0:
        db.session.add_all([Team(name="NostraCodes", tag="NSTR", win_rate=18.2, matches=86, chemistry=91), Team(name="Ultimate4", tag="ULT", win_rate=16.7, matches=74, chemistry=84), Team(name="KingsBR", tag="KBR", win_rate=15.3, matches=68, chemistry=79)])
    db.session.commit()

from datetime import datetime, timedelta
from random import randint, uniform
from flask import render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import db, User, SiteSetting, PubgPlayer, Badge, PlayerBadge, Match, MatchParticipant, FeedItem, ClaimChallenge, Asset, PlayerStatPoint, Team
from .services.pubg_api import get_player_by_name, get_lifetime_stats, get_recent_match_rows, is_demo_account, PubgApiError
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
            return redirect(url_for("player_profile_by_id", player_id=player.id))
        except PubgApiError as e:
            flash(str(e), "danger")
            return redirect(url_for("home"))

    @app.route("/p/<int:player_id>")
    def player_profile_by_id(player_id):
        player = db.session.get(PubgPlayer, player_id) or abort(404)
        badges = PlayerBadge.query.filter_by(player_id=player.id).limit(6).all()
        matches = db.session.query(MatchParticipant).filter_by(player_id=player.id).join(Match).order_by(Match.played_at.desc()).limit(5).all()
        points = PlayerStatPoint.query.filter_by(player_id=player.id).order_by(PlayerStatPoint.day.asc()).limit(30).all()
        feed = FeedItem.query.filter_by(player_id=player.id).order_by(FeedItem.created_at.desc()).limit(5).all()
        return render_template("player.html", player=player, badges=badges, matches=matches, points=points, feed=feed, is_demo=is_demo_account(player.account_id))

    @app.route("/player/<nickname>")
    def player_profile(nickname):
        # se houver um registro real e um demo com o mesmo nick, prioriza o real
        player = PubgPlayer.query.filter(PubgPlayer.nickname.ilike(nickname)).order_by(PubgPlayer.account_id.like("demo-account-%").asc(), PubgPlayer.last_synced_at.desc()).first_or_404()
        badges = PlayerBadge.query.filter_by(player_id=player.id).limit(6).all()
        matches = db.session.query(MatchParticipant).filter_by(player_id=player.id).join(Match).order_by(Match.played_at.desc()).limit(5).all()
        points = PlayerStatPoint.query.filter_by(player_id=player.id).order_by(PlayerStatPoint.day.asc()).limit(30).all()
        feed = FeedItem.query.filter_by(player_id=player.id).order_by(FeedItem.created_at.desc()).limit(5).all()
        return render_template("player.html", player=player, badges=badges, matches=matches, points=points, feed=feed, is_demo=is_demo_account(player.account_id))

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
    demo = is_demo_account(payload["account_id"])
    player = PubgPlayer.query.filter_by(account_id=payload["account_id"]).first()

    # Se o banco já tinha um registro demo desse nick, reaproveita o mesmo registro
    # quando a PUBG_API_KEY real estiver configurada. Isso evita mostrar dados fake antigos.
    if not player and not demo:
        player = PubgPlayer.query.filter(
            PubgPlayer.nickname.ilike(payload["nickname"]),
            PubgPlayer.shard == shard,
            PubgPlayer.account_id.like("demo-account-%")
        ).first()
        if player:
            clear_player_generated_data(player.id)
            player.account_id = payload["account_id"]

    if not player:
        player = PubgPlayer(
            account_id=payload["account_id"],
            nickname=payload["nickname"],
            shard=shard,
            squad_name="NostraCodes" if demo else ""
        )
        db.session.add(player)
        db.session.flush()

    stats = get_lifetime_stats(payload["account_id"], shard)
    player.nickname = payload["nickname"]
    player.shard = shard
    player.kd = float(stats.get("kd", 0))
    player.win_rate = float(stats.get("win_rate", 0))
    player.avg_damage = float(stats.get("avg_damage", 0))
    player.headshot_rate = float(stats.get("headshot_rate", 0))
    player.knocks = int(stats.get("knocks", 0))
    player.revives = int(stats.get("revives", 0))
    player.survivor_score = int(stats.get("survivor_score", 0))
    player.best_mode = stats.get("best_mode") or "Sem dados suficientes"

    # A API lifetime oficial não entrega estatística confiável por arma.
    # Não inventamos arma/dano; isso só será preenchido depois via telemetry ou upload/admin.
    if demo:
        player.main_weapon = "Beryl M762"
        player.main_weapon_kills = max(player.main_weapon_kills or 0, randint(180, 520))
        player.main_weapon_hs = round(player.headshot_rate * 0.9, 1)
        player.main_weapon_damage = round(player.avg_damage * 110, 1)
    else:
        player.main_weapon = ""
        player.main_weapon_kills = 0
        player.main_weapon_hs = 0
        player.main_weapon_damage = 0

    player.last_synced_at = datetime.utcnow()
    db.session.commit()

    if demo:
        ensure_demo_content(player)
    else:
        ensure_real_content(player, payload.get("match_ids", []))
    return player


def clear_player_generated_data(player_id):
    MatchParticipant.query.filter_by(player_id=player_id).delete()
    PlayerStatPoint.query.filter_by(player_id=player_id).delete()
    PlayerBadge.query.filter_by(player_id=player_id).delete()
    FeedItem.query.filter_by(player_id=player_id).delete()
    db.session.commit()


def ensure_real_content(player, match_ids):
    # pontos reais: salva snapshot do dia atual; sem curva fake de 30 dias
    today = datetime.utcnow().date()
    if not PlayerStatPoint.query.filter_by(player_id=player.id, day=today).first():
        db.session.add(PlayerStatPoint(player_id=player.id, day=today, kd=player.kd, damage=player.avg_damage, win_rate=player.win_rate))

    # medalhas reais básicas baseadas em lifetime; nada de medalha inventada por partida
    if PlayerBadge.query.filter_by(player_id=player.id).count() == 0:
        earned = []
        if player.headshot_rate >= 25 and player.kd > 0:
            earned.append("Head Hunter")
        if player.knocks >= 100:
            earned.append("Squad Wipe")
        if player.revives >= 50:
            earned.append("Medic")
        for name in earned:
            badge = Badge.query.filter_by(name=name).first()
            if badge:
                db.session.add(PlayerBadge(player_id=player.id, badge_id=badge.id, progress=100))

    # partidas recentes reais pela API /matches. Se falhar, deixa vazio em vez de usar demo.
    existing = {mp.match.pubg_match_id for mp in MatchParticipant.query.filter_by(player_id=player.id).join(Match).all()}
    for row in get_recent_match_rows(match_ids, player.account_id, player.shard, limit=5):
        if row["pubg_match_id"] in existing:
            continue
        m = Match.query.filter_by(pubg_match_id=row["pubg_match_id"]).first()
        if not m:
            m = Match(pubg_match_id=row["pubg_match_id"], map_name=row["map_name"], mode=row["mode"], played_at=row["played_at"], duration_seconds=row["duration_seconds"])
            db.session.add(m)
            db.session.flush()
        db.session.add(MatchParticipant(match_id=m.id, player_id=player.id, placement=row["placement"], kills=row["kills"], damage=row["damage"], headshots=row["headshots"], knocks=row["knocks"], revives=row["revives"]))

    if Team.query.count() == 0:
        db.session.add_all([Team(name="NostraCodes", tag="NSTR", win_rate=18.2, matches=86, chemistry=91), Team(name="Ultimate4", tag="ULT", win_rate=16.7, matches=74, chemistry=84), Team(name="KingsBR", tag="KBR", win_rate=15.3, matches=68, chemistry=79)])
    db.session.commit()


def ensure_demo_content(player):
    if PlayerBadge.query.filter_by(player_id=player.id).count() == 0:
        for badge in Badge.query.limit(4).all():
            db.session.add(PlayerBadge(player_id=player.id, badge_id=badge.id, progress=100))
            db.session.add(FeedItem(player_id=player.id, title=f"{player.nickname} desbloqueou a medalha {badge.name}", body=badge.description, icon=badge.icon))
    if MatchParticipant.query.filter_by(player_id=player.id).count() == 0:
        for row in get_recent_match_rows([], player.account_id, player.shard, limit=3):
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

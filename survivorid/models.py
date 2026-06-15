from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, default="")


class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(60), default="general")
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PubgPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    nickname = db.Column(db.String(120), nullable=False, index=True)
    shard = db.Column(db.String(40), default="steam")
    country = db.Column(db.String(80), default="Brazil")
    role = db.Column(db.String(80), default="Entry Fragger")
    squad_name = db.Column(db.String(120), default="")
    avatar_url = db.Column(db.String(255), default="")
    banner_url = db.Column(db.String(255), default="")
    is_claimed = db.Column(db.Boolean, default=False)
    claimed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    claimed_at = db.Column(db.DateTime, nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    kd = db.Column(db.Float, default=0)
    win_rate = db.Column(db.Float, default=0)
    avg_damage = db.Column(db.Float, default=0)
    headshot_rate = db.Column(db.Float, default=0)
    knocks = db.Column(db.Integer, default=0)
    revives = db.Column(db.Integer, default=0)
    survivor_score = db.Column(db.Integer, default=0)
    best_mode = db.Column(db.String(80), default="Squad FPP")
    best_map = db.Column(db.String(80), default="Erangel")
    main_weapon = db.Column(db.String(80), default="Beryl M762")
    main_weapon_kills = db.Column(db.Integer, default=0)
    main_weapon_hs = db.Column(db.Float, default=0)
    main_weapon_damage = db.Column(db.Float, default=0)

    owner = db.relationship("User", foreign_keys=[claimed_by_id])


class PlayerStatPoint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=False)
    day = db.Column(db.Date, nullable=False)
    kd = db.Column(db.Float, default=0)
    damage = db.Column(db.Float, default=0)
    win_rate = db.Column(db.Float, default=0)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pubg_match_id = db.Column(db.String(255), unique=True, nullable=False)
    map_name = db.Column(db.String(80), default="Erangel")
    mode = db.Column(db.String(80), default="Squad FPP")
    played_at = db.Column(db.DateTime, default=datetime.utcnow)
    duration_seconds = db.Column(db.Integer, default=0)


class MatchParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=False)
    placement = db.Column(db.Integer, default=0)
    kills = db.Column(db.Integer, default=0)
    damage = db.Column(db.Float, default=0)
    headshots = db.Column(db.Integer, default=0)
    knocks = db.Column(db.Integer, default=0)
    revives = db.Column(db.Integer, default=0)
    medals_json = db.Column(db.Text, default="[]")

    match = db.relationship("Match")
    player = db.relationship("PubgPlayer")


class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    tier = db.Column(db.String(40), default="BRONZE")
    description = db.Column(db.Text, default="")
    icon = db.Column(db.String(80), default="bi-award-fill")
    image_url = db.Column(db.String(255), default="")
    category = db.Column(db.String(80), default="general")


class PlayerBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badge.id"), nullable=False)
    progress = db.Column(db.Integer, default=100)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    badge = db.relationship("Badge")


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    tag = db.Column(db.String(20), default="")
    logo_url = db.Column(db.String(255), default="")
    win_rate = db.Column(db.Float, default=0)
    matches = db.Column(db.Integer, default=0)
    chemistry = db.Column(db.Integer, default=0)


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=False)
    role = db.Column(db.String(80), default="Player")


class ClaimChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    objective = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(40), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User")
    player = db.relationship("PubgPlayer")


class FeedItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("pubg_player.id"), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, default="")
    icon = db.Column(db.String(80), default="bi-trophy-fill")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    player = db.relationship("PubgPlayer")

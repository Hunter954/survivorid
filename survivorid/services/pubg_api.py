import os
import random
from datetime import datetime, timedelta
import requests

BASE = "https://api.pubg.com/shards/{shard}"


class PubgApiError(Exception):
    pass


def api_key():
    return os.getenv("PUBG_API_KEY", "").strip()


def demo_mode():
    return os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes"}


def is_demo_account(account_id):
    return str(account_id or "").startswith("demo-account-")


def headers(auth=True):
    h = {"Accept": "application/vnd.api+json"}
    key = api_key()
    if auth and key:
        h["Authorization"] = f"Bearer {key}"
    return h


def request_json(url, auth=True, timeout=15):
    r = requests.get(url, headers=headers(auth=auth), timeout=timeout)
    if r.status_code == 404:
        raise PubgApiError("Jogador ou partida não encontrado nessa plataforma.")
    if r.status_code >= 400:
        try:
            detail = r.json().get("errors", [{}])[0].get("detail", "")
        except Exception:
            detail = r.text[:120]
        raise PubgApiError(f"Erro PUBG API: {r.status_code} {detail}".strip())
    return r.json()


def get_player_by_name(nickname, shard="steam"):
    nickname = nickname.strip()
    if not nickname:
        raise PubgApiError("Informe um nick PUBG.")

    if not api_key():
        if demo_mode():
            return demo_player_payload(nickname, shard)
        raise PubgApiError("PUBG_API_KEY não configurada. Defina a variável no Railway ou ative DEMO_MODE=true apenas para demonstração.")

    url = f"{BASE.format(shard=shard)}/players?filter[playerNames]={nickname}"
    data = request_json(url, auth=True).get("data", [])
    if not data:
        raise PubgApiError("Jogador não encontrado.")
    p = data[0]
    attrs = p.get("attributes", {})
    return {
        "account_id": p.get("id"),
        "nickname": attrs.get("name", nickname),
        "shard": shard,
        "match_ids": [m.get("id") for m in p.get("relationships", {}).get("matches", {}).get("data", []) if m.get("id")]
    }


def get_lifetime_stats(account_id, shard="steam"):
    if is_demo_account(account_id):
        return demo_stats(account_id)
    if not api_key():
        return {}
    url = f"{BASE.format(shard=shard)}/players/{account_id}/seasons/lifetime"
    try:
        raw = request_json(url, auth=True)
    except PubgApiError:
        return {}
    return parse_lifetime_stats(raw)


def parse_lifetime_stats(raw):
    """Converte o JSON oficial lifetime da PUBG API para os campos do MVP.
    A API oficial não entrega estatística por arma no lifetime; isso fica zerado até processar telemetry.
    """
    modes = raw.get("data", {}).get("attributes", {}).get("gameModeStats", {}) or {}
    totals = {
        "kills": 0, "losses": 0, "wins": 0, "rounds": 0, "damage": 0.0,
        "headshots": 0, "dbnos": 0, "revives": 0, "time": 0,
    }
    best_mode = ""
    best_mode_kd = -1
    best_mode_win = 0

    for mode, s in modes.items():
        rounds = int(s.get("roundsPlayed") or 0)
        kills = int(s.get("kills") or 0)
        losses = int(s.get("losses") or max(rounds - int(s.get("wins") or 0), 1))
        wins = int(s.get("wins") or 0)
        damage = float(s.get("damageDealt") or 0)
        if rounds <= 0 and kills <= 0 and damage <= 0:
            continue
        kd = kills / max(losses, 1)
        win_rate = (wins / max(rounds, 1)) * 100
        if kd > best_mode_kd and rounds >= 3:
            best_mode_kd = kd
            best_mode = human_mode(mode)
            best_mode_win = win_rate
        totals["kills"] += kills
        totals["losses"] += losses
        totals["wins"] += wins
        totals["rounds"] += rounds
        totals["damage"] += damage
        totals["headshots"] += int(s.get("headshotKills") or 0)
        totals["dbnos"] += int(s.get("dBNOs") or 0)
        totals["revives"] += int(s.get("revives") or 0)
        totals["time"] += int(s.get("timeSurvived") or 0)

    rounds = max(totals["rounds"], 1)
    kills = totals["kills"]
    kd = kills / max(totals["losses"], 1)
    win_rate = (totals["wins"] / rounds) * 100
    avg_damage = totals["damage"] / rounds
    hs_rate = (totals["headshots"] / max(kills, 1)) * 100
    survivor_score = int(min(1000, kd * 135 + win_rate * 12 + avg_damage * 0.55 + hs_rate * 3 + min(totals["revives"], 500) * 0.15))

    return {
        "kd": round(kd, 2),
        "win_rate": round(win_rate, 1),
        "avg_damage": round(avg_damage, 1),
        "headshot_rate": round(hs_rate, 1),
        "knocks": totals["dbnos"],
        "revives": totals["revives"],
        "survivor_score": max(0, survivor_score),
        "best_mode": best_mode or "Sem dados suficientes",
        "best_mode_win": round(best_mode_win, 1),
        "rounds": totals["rounds"],
        "kills": kills,
    }


def human_mode(mode):
    names = {
        "solo": "Solo TPP", "solo-fpp": "Solo FPP", "duo": "Duo TPP", "duo-fpp": "Duo FPP",
        "squad": "Squad TPP", "squad-fpp": "Squad FPP",
        "normal-squad-fpp": "Squad FPP", "normal-duo-fpp": "Duo FPP", "normal-solo-fpp": "Solo FPP",
    }
    return names.get(mode, mode.replace("-", " ").title())


def get_recent_match_rows(match_ids, account_id, shard="steam", limit=5):
    if is_demo_account(account_id):
        return demo_recent_matches(account_id, account_id)
    rows = []
    for mid in (match_ids or [])[:limit]:
        try:
            rows.append(get_match_participant_row(mid, account_id, shard))
        except Exception:
            continue
    return [r for r in rows if r]


def get_match_participant_row(match_id, account_id, shard="steam"):
    # Match endpoint normalmente não consome rate limit e pode ser acessado pelo ID da partida.
    url = f"{BASE.format(shard=shard)}/matches/{match_id}"
    raw = request_json(url, auth=False)
    data = raw.get("data", {})
    attrs = data.get("attributes", {}) or {}
    included = raw.get("included", []) or []
    participant = None
    for item in included:
        if item.get("type") != "participant":
            continue
        stats = item.get("attributes", {}).get("stats", {}) or {}
        if stats.get("playerId") == account_id:
            participant = stats
            break
    if not participant:
        return None

    created_at = attrs.get("createdAt")
    try:
        played_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None) if created_at else datetime.utcnow()
    except Exception:
        played_at = datetime.utcnow()

    mode = human_mode(attrs.get("gameMode", ""))
    return {
        "pubg_match_id": match_id,
        "map_name": attrs.get("mapName") or "Mapa desconhecido",
        "mode": mode,
        "played_at": played_at,
        "duration_seconds": int(attrs.get("duration") or participant.get("timeSurvived") or 0),
        "placement": int(participant.get("winPlace") or 0),
        "kills": int(participant.get("kills") or 0),
        "damage": float(participant.get("damageDealt") or 0),
        "headshots": int(participant.get("headshotKills") or 0),
        "knocks": int(participant.get("DBNOs") or participant.get("dBNOs") or 0),
        "revives": int(participant.get("revives") or 0),
        "medals": infer_match_medals(participant),
    }


def infer_match_medals(stats):
    medals = []
    if int(stats.get("headshotKills") or 0) >= 3:
        medals.append("Head Hunter")
    if int(stats.get("kills") or 0) >= 10:
        medals.append("Monster Match")
    if int(stats.get("revives") or 0) >= 2:
        medals.append("Medic")
    if int(stats.get("longestKill") or 0) >= 300:
        medals.append("Long Shot")
    return medals


def demo_player_payload(nickname, shard):
    safe = nickname.replace(" ", "_")
    return {
        "account_id": f"demo-account-{safe.lower()}-{shard}",
        "nickname": safe,
        "shard": shard,
        "match_ids": [f"demo-match-{safe.lower()}-{i}" for i in range(1, 4)]
    }


def demo_stats(account_id):
    seed = sum(ord(c) for c in account_id)
    random.seed(seed)
    kd = round(random.uniform(1.4, 4.8), 2)
    win = round(random.uniform(6, 22), 1)
    dmg = int(random.uniform(230, 540))
    hs = round(random.uniform(18, 39), 1)
    knocks = random.randint(200, 1500)
    revives = random.randint(50, 420)
    score = min(999, int(kd * 130 + win * 13 + dmg * 0.55 + hs * 4))
    return {"kd": kd, "win_rate": win, "avg_damage": dmg, "headshot_rate": hs, "knocks": knocks, "revives": revives, "survivor_score": score, "best_mode": "Squad FPP"}


def demo_recent_matches(player_id, nickname):
    maps = ["Erangel", "Miramar", "Deston", "Taego", "Vikendi"]
    modes = ["Squad FPP", "Duo FPP", "Squad TPP"]
    rows = []
    for i in range(3):
        rows.append({
            "pubg_match_id": f"demo-{nickname}-{player_id}-{i}",
            "map_name": maps[i % len(maps)],
            "mode": modes[i % len(modes)],
            "played_at": datetime.utcnow() - timedelta(hours=i * 6 + 1),
            "duration_seconds": random.randint(1400, 2100),
            "placement": [1, 4, 7][i],
            "kills": [12, 6, 3][i],
            "damage": [1430, 720, 512][i],
            "headshots": [4, 2, 1][i],
            "knocks": [9, 4, 2][i],
            "revives": [2, 1, 0][i],
            "medals": ["Head Hunter", "Clutch Master"] if i == 0 else ["Long Shot"]
        })
    return rows

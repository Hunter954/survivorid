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
    return os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes"}


def headers():
    key = api_key()
    return {"Authorization": f"Bearer {key}", "Accept": "application/vnd.api+json"}


def get_player_by_name(nickname, shard="steam"):
    nickname = nickname.strip()
    if not nickname:
        raise PubgApiError("Informe um nick PUBG.")
    if not api_key() and demo_mode():
        return demo_player_payload(nickname, shard)
    if not api_key():
        raise PubgApiError("PUBG_API_KEY não configurada.")
    url = f"{BASE.format(shard=shard)}/players?filter[playerNames]={nickname}"
    r = requests.get(url, headers=headers(), timeout=12)
    if r.status_code == 404:
        raise PubgApiError("Jogador não encontrado nessa plataforma.")
    if r.status_code >= 400:
        raise PubgApiError(f"Erro PUBG API: {r.status_code}")
    data = r.json().get("data", [])
    if not data:
        raise PubgApiError("Jogador não encontrado.")
    p = data[0]
    attrs = p.get("attributes", {})
    return {
        "account_id": p.get("id"),
        "nickname": attrs.get("name", nickname),
        "shard": shard,
        "match_ids": [m.get("id") for m in p.get("relationships", {}).get("matches", {}).get("data", [])]
    }


def get_lifetime_stats(account_id, shard="steam"):
    if not api_key() and demo_mode():
        return demo_stats(account_id)
    if not api_key():
        return {}
    url = f"{BASE.format(shard=shard)}/players/{account_id}/seasons/lifetime"
    r = requests.get(url, headers=headers(), timeout=12)
    if r.status_code >= 400:
        return {}
    return r.json()


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
    return {"kd": kd, "win_rate": win, "avg_damage": dmg, "headshot_rate": hs, "knocks": knocks, "revives": revives, "survivor_score": score}


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

"""
Onces probables desde futbolfantasy.com. Devuelve {player_id: {status, pct}} emparejando por nombre.
Si algo falla devuelve None y el motor usa la caché o 'desconocido' (factor 1.0).
"""
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE = "https://www.futbolfantasy.com/laliga/equipos/{slug}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
# teams-master id -> slug de futbolfantasy (difiere del slug de LaLiga)
FF_SLUGS = {
    "21": "alaves", "3": "athletic", "2": "atletico", "4": "barcelona", "5": "betis", "6": "celta",
    "26": "deportivo", "7": "elche", "8": "espanyol", "9": "getafe", "11": "levante", "12": "malaga",
    "13": "osasuna", "49": "racing", "14": "rayo-vallecano", "15": "real-madrid", "16": "real-sociedad",
    "17": "sevilla", "18": "valencia", "20": "villarreal",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def parse_team_html(html: str) -> list:
    """[{name, slug, status: starter|bench|injured|doubt, pct, position}] de una página de equipo."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for w in soup.select(".camiseta-wrapper[data-onceff]"):
        if "tipo_campo" not in (w.get("class") or []):
            continue  # duplicados de la vista lista
        a = w.select_one("a.camiseta") or w.select_one("a")
        if not a:
            continue
        name = (w.select_one(".truncate-name") or a).get_text(" ", strip=True)
        name = re.sub(r"\s*\d+\s*%.*$", "", name).strip()
        if not name:
            continue
        m = re.search(r"/jugadores/([^/?#]+)", a.get("href") or "")
        slug = m.group(1) if m else None
        pct_raw = a.get("data-probabilidad") or ""
        pm = re.search(r"(\d+)", pct_raw) or re.search(r"(\d+)\s*%", w.get_text(" ", strip=True))
        pct = int(pm.group(1)) if pm else (70 if w.get("data-onceff") == "titular" else 30)
        lesion = str(a.get("data-lesion", "-1"))
        sanc = str(a.get("data-sancionado", "0"))
        if lesion == "0" or sanc not in ("0", "", "None"):
            status = "injured"
        elif lesion in ("1", "2"):
            status = "doubt"
        else:
            status = "starter" if w.get("data-onceff") == "titular" else "bench"
        key = slug or norm(name)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "slug": slug, "status": status, "pct": pct, "position": w.get("data-posicion")})
    return out


def fetch_team(slug: str, timeout=15) -> list | None:
    try:
        r = requests.get(BASE.format(slug=slug), headers=HEADERS, timeout=timeout)
        if r.status_code != 200 or len(r.text) < 20000:
            return None
        rows = parse_team_html(r.text)
        return rows if len(rows) >= 11 else None
    except (requests.RequestException, ValueError):
        return None


def match_players(rows: list, club_players: list) -> dict:
    """Empareja filas scrapeadas con jugadores de LaLiga (norm_player) del mismo club -> {player_id: {status,pct}}."""
    out = {}
    by_nick, by_last = {}, {}
    for p in club_players:
        by_nick.setdefault(norm(p["nickname"]), []).append(p)
        toks = norm(p.get("name") or p["nickname"]).split()
        if toks:
            by_last.setdefault(toks[-1], []).append(p)
    for r in rows:
        n = norm(r["name"])
        slug_toks = norm((r.get("slug") or "").replace("-", " ")).split()
        cands = by_nick.get(n) or []
        if not cands and slug_toks:
            cands = by_last.get(slug_toks[-1]) or []
        if not cands:
            toks = n.replace(".", " ").split()
            if toks:
                cands = by_last.get(toks[-1]) or [p for p in club_players if toks[-1] in norm(p["nickname"]).split()]
        if len(cands) == 1:
            out[cands[0]["id"]] = {"status": r["status"], "pct": r["pct"]}
    return out


def fetch_probables(snap, cfg, cache_path: str, clubs: set, now: datetime) -> tuple[dict, str]:
    """Devuelve ({player_id: {...}}, resumen). Usa caché si el scraping falla."""
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    result, ok, failed = {}, 0, []
    for tid in sorted(clubs):
        slug = FF_SLUGS.get(str(tid)) or (snap.teams_master.get(str(tid)) or {}).get("slug")
        if not slug:
            continue
        club_players = [p for p in snap.players.values() if p["teamId"] == str(tid) and p["playerStatus"] != "out_of_league"]
        rows = fetch_team(slug)
        time.sleep(cfg.probable.request_delay)
        if rows:
            matched = match_players(rows, club_players)
            if len(matched) >= 8:
                result.update(matched)
                cache[str(tid)] = {"at": now.isoformat(), "data": matched}
                ok += 1
                continue
        failed.append(snap.club_short(tid))
        c = cache.get(str(tid))
        if c and now - datetime.fromisoformat(c["at"]) < timedelta(hours=cfg.probable.cache_hours):
            result.update(c["data"])
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    summary = f"probables: {ok}/{len(clubs)} clubes" + (f" (caído: {', '.join(failed)})" if failed else "")
    return result, summary

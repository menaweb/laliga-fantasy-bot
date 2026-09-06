"""Construye un Snapshot desde un directorio de JSON (fixtures o data/raw_*), sin red."""
import json
import os

from fantasy.models import norm_player
from fantasy.state import Snapshot


def _j(d, name, default=None):
    p = os.path.join(d, f"{name}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def snapshot_from_dir(d: str) -> Snapshot:
    s = Snapshot()
    s.league_id = str(_j(d, "league", {}).get("id") or "017900934")
    s.team = _j(d, "team", {})
    s.team_id = str(s.team.get("id") or "37682094")
    s.manager_id = str(s.team.get("managerId") or "")
    s.week = _j(d, "week", {})
    wn = int(s.week.get("weekNumber") or 0)
    for w in (wn, wn + 1):
        cal = _j(d, f"calendar_{w}")
        if cal is not None:
            s.calendar[w] = cal
    m = _j(d, "money", 0)
    s.money = int(m.get("teamMoney", 0)) if isinstance(m, dict) else int(m or 0)
    s.lineup = _j(d, "lineup", {})
    s.market = _j(d, "market", [])
    s.players = {p["id"]: p for p in map(norm_player, _j(d, "players", []))}
    s.teams_master = {str(t["id"]): {"shortName": t.get("shortName"), "slug": t.get("slug"), "name": t.get("name")}
                      for t in _j(d, "teams_master", [])}
    s.standing = _j(d, "standing", [])
    s.activity = _j(d, "activity_0", [])
    s.formations = _j(d, "formations_free", ["4,4,2"])
    for f in os.listdir(d):
        if f.startswith("team_rival") and f.endswith(".json"):
            t = _j(d, f[:-5], {})
            s.rivals[str(t.get("id") or f)] = t
        if f.startswith("received_offers_") and f.endswith(".json"):
            pass
    ro = _j(d, "received_offers_mine0")
    if ro is not None and s.squad_items():
        first_on_sale = next((it for it in s.squad_items() if it.get("playerMarket")), None)
        if first_on_sale:
            s.offers[str(first_on_sale.get("playerTeamId"))] = ro
    return s

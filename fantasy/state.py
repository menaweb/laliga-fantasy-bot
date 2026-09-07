"""
Estado del motor: snapshot de la liga (fetch + versión compacta), histórico de valores
diarios, libro (ledger) de pujas/listados y log de decisiones. Todo son JSON/MD en state/.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone

from .models import norm_player
from .client import FantasyClient, ApiError

ISO = "%Y-%m-%dT%H:%M:%S%z"


def parse_dt(s):
    """'2026-09-05T21:00:00+02:00' -> datetime aware. None si no se puede."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


class Snapshot:
    """Todo lo que la estrategia necesita de la API en un run. Solo lectura."""

    def __init__(self):
        self.fetched_at = None
        self.league_id = None
        self.team_id = None
        self.manager_id = None
        self.week = {}
        self.calendar = {}          # {week_number: [matches]}
        self.team = {}
        self.money = 0
        self.investment = 0         # dinero comprometido en pujas pendientes (teamInvestment)
        self.lineup = {}
        self.market = []
        self.players = {}           # id -> norm_player (toda la liga)
        self.teams_master = {}      # id -> {shortName, slug, name}
        self.standing = []
        self.activity = []
        self.formations = []
        self.offers = {}            # playerTeamId -> [ofertas recibidas]
        self.rivals = {}            # team_id -> team json (plantilla rival)

    # ---------- fetch ----------
    @classmethod
    def fetch(cls, c: FantasyClient, cfg, cache: dict | None = None) -> "Snapshot":
        cache = cache or {}
        s = cls()
        s.fetched_at = datetime.now(timezone.utc)
        s.league_id = str(cfg.league_id)
        now = s.fetched_at

        s.team_id = cache.get("team_id")
        s.manager_id = cache.get("manager_id")
        if not s.team_id:
            me = c.me() or {}
            s.manager_id = str(me.get("id"))
            leagues = c.leagues() or []
            lg = next((l for l in leagues if str(l.get("id")) == s.league_id), None)
            if not lg:
                raise ApiError(f"La liga {s.league_id} no está en la cuenta")
            s.team_id = str(((lg.get("team") or {}).get("id")) or "")
            if not s.team_id:
                raise ApiError("No se pudo identificar el equipo en la liga")

        s.week = c.current_week() or {}
        wn = int(s.week.get("weekNumber") or 0)
        for w in (wn, wn + 1):
            if w:
                s.calendar[w] = c.calendar(w) or []

        s.team = c.team(s.league_id, s.team_id) or {}
        money = c.money(s.team_id)
        s.money = int(money.get("teamMoney", 0)) if isinstance(money, dict) else int(money or 0)
        s.investment = int(money.get("teamInvestment", 0) or 0) if isinstance(money, dict) else 0
        s.lineup = c.lineup(s.team_id) or {}
        s.market = c.market(s.league_id) or []
        s.players = {p["id"]: p for p in (norm_player(x) for x in (c.players() or []))}

        tm_cache = cache.get("teams_master")
        if tm_cache and _fresh(cache.get("teams_master_at"), now, hours=24 * 7):
            s.teams_master = tm_cache
        else:
            s.teams_master = {str(t["id"]): {"shortName": t.get("shortName"), "slug": t.get("slug"), "name": t.get("name")}
                              for t in (c.teams_master() or []) if isinstance(t, dict)}
            cache["teams_master"], cache["teams_master_at"] = s.teams_master, now.strftime(ISO)

        s.standing = c.standing(s.league_id) or []
        s.activity = c.activity(s.league_id, 0) or []

        fm_cache = cache.get("formations")
        if fm_cache and _fresh(cache.get("formations_at"), now, hours=24 * 30):
            s.formations = fm_cache
        else:
            s.formations = c.formations("free") or []
            cache["formations"], cache["formations_at"] = s.formations, now.strftime(ISO)

        for it in s.squad_items():
            if it.get("playerMarket"):
                ptid = it.get("playerTeamId")
                try:
                    s.offers[str(ptid)] = c.received_offers(s.league_id, ptid) or []
                except ApiError as e:
                    if "429" in str(e):
                        raise
                    s.offers[str(ptid)] = []

        # plantillas rivales (para cláusulas), con caché
        rivals_cache = cache.get("rivals") or {}
        if rivals_cache and _fresh(cache.get("rivals_at"), now, hours=cfg.run.rivals_cache_hours):
            s.rivals = rivals_cache
        else:
            for e in s.standing:
                t = e.get("team") or e
                tid = str(t.get("id"))
                if tid == s.team_id:
                    continue
                s.rivals[tid] = c.team(s.league_id, tid) or {}
            cache["rivals"], cache["rivals_at"] = s.rivals, now.strftime(ISO)

        cache["team_id"], cache["manager_id"] = s.team_id, s.manager_id
        return s

    # ---------- accesores ----------
    @property
    def week_number(self) -> int:
        return int(self.week.get("weekNumber") or 0)

    @property
    def is_live(self) -> bool:
        return bool(self.week.get("isLive"))

    def squad_items(self) -> list:
        return [it for it in (self.team.get("players") or []) if isinstance(it, dict)]

    def squad(self) -> list:
        """Lista de {ptid, player(norm), buyoutClause, lockedEnd, onSale(playerMarket), isShielded}."""
        out = []
        for it in self.squad_items():
            p = norm_player(it.get("playerMaster") or {})
            out.append({
                "ptid": str(it.get("playerTeamId")),
                "player": p,
                "buyoutClause": int(it.get("buyoutClause") or 0),
                "lockedEnd": parse_dt(it.get("buyoutClauseLockedEndTime")),
                "onSale": it.get("playerMarket") or None,
                "isShielded": bool(it.get("isShielded")),
            })
        return out

    @property
    def projected_money(self) -> int:
        """Saldo menos pujas pendientes (la API no descuenta las pujas de teamMoney)."""
        return self.money - self.investment

    def my_bids(self) -> dict:
        """{market_id: {id, money, status}} de mis pujas según el propio mercado."""
        out = {}
        for it in self.market:
            b = it.get("bid")
            if isinstance(b, dict) and b.get("status") in (None, "pending"):
                out[str(it.get("id"))] = {"id": str(b.get("id")), "money": int(b.get("money") or 0),
                                          "player_id": str((it.get("playerMaster") or {}).get("id"))}
        return out

    def rival_squads(self) -> list:
        """[{team_id, manager, ptid, player, buyoutClause, lockedEnd, onSale}] de todos los rivales."""
        out = []
        for tid, t in self.rivals.items():
            mgr = ((t.get("manager") or {}).get("managerName")) or tid
            for it in (t.get("players") or []):
                p = norm_player(it.get("playerMaster") or {})
                out.append({"team_id": tid, "manager": mgr, "ptid": str(it.get("playerTeamId")), "player": p,
                            "buyoutClause": int(it.get("buyoutClause") or 0),
                            "lockedEnd": parse_dt(it.get("buyoutClauseLockedEndTime")),
                            "onSale": it.get("playerMarket") or None})
        return out

    def current_xi(self) -> dict:
        """{'formation': [d,m,f], 'goalkeeper': [ptid], 'defender': [...], 'midfield': [...], 'striker': [...]}"""
        f = self.lineup.get("formation") or {}
        out = {"formation": list(f.get("tacticalFormation") or [])}
        for line in ("goalkeeper", "defender", "midfield", "striker"):
            out[line] = [str(e.get("playerTeamId")) for e in (f.get(line) or []) if isinstance(e, dict)]
        return out

    def club_short(self, team_id) -> str:
        return (self.teams_master.get(str(team_id)) or {}).get("shortName") or str(team_id)

    def matches(self, week=None) -> list:
        return self.calendar.get(week or self.week_number) or []

    def match_for_club(self, team_id, week=None):
        tid = str(team_id)
        for m in self.matches(week):
            if str(m.get("localId")) == tid or str(m.get("visitorId")) == tid:
                return m
        return None

    def to_compact(self) -> dict:
        """Versión compacta para state/snapshot.json (sin imágenes ni stats)."""
        return {
            "fetched_at": self.fetched_at.strftime(ISO) if self.fetched_at else None,
            "league_id": self.league_id, "team_id": self.team_id, "manager_id": self.manager_id,
            "week": self.week, "money": self.money, "investment": self.investment,
            "team": {"teamValue": self.team.get("teamValue"), "teamPoints": self.team.get("teamPoints"),
                     "position": self.team.get("position"), "playersNumber": self.team.get("playersNumber")},
            "squad": [{"ptid": s["ptid"], **{k: s["player"][k] for k in ("id", "nickname", "positionId", "teamId", "marketValue", "points", "averagePoints", "playerStatus")},
                       "buyoutClause": s["buyoutClause"], "lockedEnd": s["lockedEnd"].strftime(ISO) if s["lockedEnd"] else None,
                       "onSale": bool(s["onSale"])} for s in self.squad()],
            "xi": self.current_xi(),
            "market": [{"id": str(it.get("id")), "discr": it.get("discr"), "salePrice": it.get("salePrice"),
                        "expirationDate": it.get("expirationDate"), "numberOfBids": it.get("numberOfBids"),
                        "seller": str((it.get("sellerTeam") or {}).get("id") or ""),
                        "myBid": (it.get("bid") or {}).get("money"),
                        **{k: norm_player(it.get("playerMaster") or {})[k] for k in ("id", "nickname", "positionId", "marketValue", "points", "averagePoints", "playerStatus")}}
                       for it in self.market],
            "standing": [{"position": e.get("position"), "points": e.get("points"),
                          "team_id": str((e.get("team") or e).get("id")),
                          "manager": ((e.get("team") or e).get("manager") or {}).get("managerName"),
                          "teamValue": (e.get("team") or e).get("teamValue")} for e in self.standing],
        }


def _fresh(stamp: str | None, now: datetime, hours: float) -> bool:
    dt = parse_dt(stamp) if stamp else None
    return bool(dt) and (now - dt) < timedelta(hours=hours)


class ValueHistory:
    """state/values/YYYY-MM-DD.json = {playerId: marketValue}. Una foto por día."""

    def __init__(self, state_dir):
        self.dir = os.path.join(state_dir, "values")
        os.makedirs(self.dir, exist_ok=True)
        self._cache = {}

    def _path(self, day: str):
        return os.path.join(self.dir, f"{day}.json")

    def record_today(self, players: dict, today: str, keep_days=45) -> bool:
        if os.path.exists(self._path(today)):
            return False
        _write_json(self._path(today), {pid: p["marketValue"] for pid, p in players.items() if p.get("marketValue")})
        for f in sorted(glob.glob(os.path.join(self.dir, "*.json")))[:-keep_days]:
            os.remove(f)
        return True

    def _load(self, day: str) -> dict:
        if day not in self._cache:
            self._cache[day] = _read_json(self._path(day), {})
        return self._cache[day]

    def days(self) -> list:
        return sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(self.dir, "*.json")))

    def trend(self, pid: str, today: str, days: int = 7):
        """(mv_hoy - mv_hace_n)/mv_hace_n usando el día más antiguo dentro de la ventana. None si no hay datos."""
        avail = [d for d in self.days() if d <= today]
        if len(avail) < 2:
            return None
        cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
        older = [d for d in avail if d >= cutoff and d < today]
        if not older:
            return None
        base = self._load(older[0]).get(str(pid))
        cur = self._load(today).get(str(pid))
        if not base or not cur:
            return None
        return (cur - base) / base


class Ledger:
    """state/ledger.json: pujas activas, listados propios, ofertas gestionadas, historial de runs."""

    def __init__(self, state_dir):
        self.path = os.path.join(state_dir, "ledger.json")
        d = _read_json(self.path, {})
        self.bids = d.get("bids", [])
        self.listings = d.get("listings", [])
        self.handled_offers = d.get("handled_offers", [])
        self.runs = d.get("runs", [])
        self.live_writes_seen = d.get("live_writes_seen", [])

    def save(self):
        _write_json(self.path, {"bids": self.bids, "listings": self.listings, "handled_offers": self.handled_offers[-200:],
                                "runs": self.runs[-500:], "live_writes_seen": self.live_writes_seen})

    def reconcile(self, snap: Snapshot):
        """Sincroniza las pujas con lo que dice el mercado (campo `bid`) y limpia listados vendidos."""
        mine = snap.my_bids()
        kept = []
        for b in self.bids:
            m = mine.get(str(b.get("market_id")))
            if not m:
                continue  # resuelta, cancelada o expirada
            b["bid_id"], b["money"] = m["id"], m["money"]
            kept.append(b)
        known = {str(b["market_id"]) for b in kept}
        for mid, m in mine.items():   # pujas hechas fuera del bot (app) o perdidas del ledger
            if mid not in known:
                kept.append({"market_id": mid, "player_id": m["player_id"], "money": m["money"], "bid_id": m["id"],
                             "placed_at": None, "reason": "detectada en el mercado"})
        self.bids = kept
        on_sale = {str((s["onSale"] or {}).get("id")) for s in snap.squad() if s["onSale"]}
        self.listings = [l for l in self.listings if str(l.get("market_id")) in on_sale]

    def pending_bid_total(self) -> int:
        return sum(int(b.get("money") or 0) for b in self.bids)

    def bid_for(self, market_id):
        return next((b for b in self.bids if str(b.get("market_id")) == str(market_id)), None)

    def add_bid(self, market_id, player_id, money, bid_id=None, reason=""):
        self.bids.append({"market_id": str(market_id), "player_id": str(player_id), "money": int(money),
                          "bid_id": bid_id, "placed_at": datetime.now(timezone.utc).strftime(ISO), "reason": reason})

    def remove_bid(self, market_id):
        self.bids = [b for b in self.bids if str(b.get("market_id")) != str(market_id)]

    def add_listing(self, market_id, player_id, price):
        self.listings.append({"market_id": str(market_id), "player_id": str(player_id), "price": int(price),
                              "listed_at": datetime.now(timezone.utc).strftime(ISO)})

    def consecutive_failures(self) -> int:
        n = 0
        for r in reversed(self.runs):
            if r.get("error"):
                n += 1
            else:
                break
        return n


class DecisionLog:
    """state/decisions/YYYY-MM-DD.md: una línea por decisión, legible por humanos."""

    def __init__(self, state_dir):
        self.dir = os.path.join(state_dir, "decisions")
        os.makedirs(self.dir, exist_ok=True)

    def append(self, day: str, header: str, lines: list):
        with open(os.path.join(self.dir, f"{day}.md"), "a", encoding="utf-8") as f:
            f.write(f"\n### {header}\n")
            for l in lines:
                f.write(f"- {l}\n")


def load_cache(state_dir) -> dict:
    return _read_json(os.path.join(state_dir, "cache.json"), {})


def save_cache(state_dir, cache: dict):
    _write_json(os.path.join(state_dir, "cache.json"), cache)


def save_snapshot(state_dir, snap: Snapshot):
    _write_json(os.path.join(state_dir, "snapshot.json"), snap.to_compact())

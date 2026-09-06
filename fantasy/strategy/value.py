"""
Valoración explicable de jugadores: puntos esperados por jornada y valor justo.
exp_points = base × disponibilidad × dificultad_rival × probable_titular
"""
from statistics import median

from ..config import POS_NAMES


class Valuer:
    def __init__(self, snap, history, probable: dict | None, cfg, today: str):
        self.s = snap
        self.h = history
        self.prob = probable or {}     # player_id -> {"status": starter|bench|injured|doubt, "pct": 0-100}
        self.cfg = cfg
        self.today = today
        self.next_week = snap.week_number + 1 if snap.is_live else snap.week_number
        self._strength = self._club_strengths()
        self._median_mv = self._medians()
        self._cache = {}

    # ---------- contexto ----------
    def _club_strengths(self) -> dict:
        """Fuerza de cada club = media del valor de sus 15 jugadores más caros. Normalizada a rango 0..1."""
        by_club = {}
        for p in self.s.players.values():
            if p["playerStatus"] == "out_of_league" or not p["teamId"]:
                continue
            by_club.setdefault(p["teamId"], []).append(p["marketValue"])
        raw = {tid: sum(sorted(v, reverse=True)[:15]) / min(15, len(v)) for tid, v in by_club.items() if v}
        if not raw:
            return {}
        lo, hi = min(raw.values()), max(raw.values())
        return {tid: (v - lo) / (hi - lo) if hi > lo else 0.5 for tid, v in raw.items()}

    def _medians(self) -> dict:
        by_pos = {}
        for p in self.s.players.values():
            if p["playerStatus"] != "out_of_league" and p["marketValue"]:
                by_pos.setdefault(p["positionId"], []).append(p["marketValue"])
        return {pos: median(v) for pos, v in by_pos.items()}

    def games_played(self, p: dict) -> int:
        if p["averagePoints"] and p["points"]:
            return max(1, round(p["points"] / p["averagePoints"]))
        if p.get("weekPoints"):
            return len(p["weekPoints"])
        return max(0, self.s.week_number - 1)

    # ---------- componentes ----------
    def base_points(self, p: dict) -> tuple[float, str]:
        lc = self.cfg.lineup
        pos = POS_NAMES.get(p["positionId"], "MED")
        med = self._median_mv.get(p["positionId"]) or 1
        prior_mv = min(8.0, lc.prior_ppg_by_pos.get(pos, 3.5) * (max(p["marketValue"], 1) / med) ** 0.35)
        ls = p.get("lastSeasonPoints") or 0
        prior = 0.6 * (ls / 34) + 0.4 * prior_mv if ls > 0 else prior_mv
        games = self.games_played(p)
        w = min(games, lc.min_games_for_full_weight) / lc.min_games_for_full_weight
        ppg = p["averagePoints"] if games else 0.0
        base = w * ppg + (1 - w) * prior
        return base, f"ppg {ppg:.1f}×{w:.1f}+prior {prior:.1f}"

    def availability(self, p: dict) -> float:
        st = p.get("playerStatus") or "unknown"
        f = self.cfg.lineup.status_factor
        return float(f.get(st, f.get("unknown", 0.85)))

    def fixture(self, p: dict) -> tuple[float, str]:
        m = self.s.match_for_club(p["teamId"], self.next_week)
        if not m:
            return 0.0, "sin partido"
        home = str(m.get("localId")) == str(p["teamId"])
        rival = str(m.get("visitorId") if home else m.get("localId"))
        lo, hi = self.cfg.lineup.fixture_range
        strength = self._strength.get(rival, 0.5)       # 1 = rival más fuerte
        factor = hi - (hi - lo) * strength + (self.cfg.lineup.home_bonus if home else 0.0)
        return factor, f"{'vs' if home else '@'} {self.s.club_short(rival)} {factor:.2f}"

    def probable(self, p: dict) -> tuple[float, str]:
        info = self.prob.get(p["id"])
        if not info:
            return 1.0, "prob ?"
        if info.get("status") == "injured":
            return 0.0, "prob lesión"
        mn = self.cfg.lineup.probable_min_factor
        pct = max(0, min(100, int(info.get("pct") or 0)))
        factor = mn + (1 - mn) * pct / 100
        return factor, f"prob {info.get('status')} {pct}%"

    # ---------- salida ----------
    def evaluate(self, p: dict) -> dict:
        pid = p["id"]
        if pid in self._cache:
            return self._cache[pid]
        base, r1 = self.base_points(p)
        av = self.availability(p)
        fx, r2 = self.fixture(p)
        pr, r3 = self.probable(p)
        exp = base * av * fx * pr
        trend = self.h.trend(pid, self.today) if self.h else None
        fair = p["marketValue"]
        if trend is not None:
            fair = int(p["marketValue"] * (1 + max(-0.10, min(0.10, trend))))
        reason = f"{exp:.1f} pts esp ({r1} · {p['playerStatus']} · {r2} · {r3}" + (f" · tend7 {trend:+.0%}" if trend is not None else "") + ")"
        out = {"exp": exp, "fair": fair, "trend": trend, "availability": av, "reason": reason}
        self._cache[pid] = out
        return out

    def exp(self, p: dict) -> float:
        return self.evaluate(p)["exp"]

    def fair(self, p: dict) -> int:
        return self.evaluate(p)["fair"]

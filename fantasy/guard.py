"""
Única capa de límites. La estrategia propone; el guard decide si una acción puede ejecutarse.
Reglas puras: sin red, sin estado global. Cualquier bug de estrategia se queda aquí.
"""
from dataclasses import dataclass
from datetime import datetime

from .config import ABSOLUTE_CAP, POS_NAMES
from .models import Action, SPENDING_KINDS
from .strategy.lineup import started_clubs
from .strategy.squad import can_field_without, count_by_pos, xi_set


@dataclass
class Verdict:
    ok: bool
    rule: str = ""


class Guard:
    def __init__(self, cfg, snap, ledger, now: datetime):
        self.cfg, self.s, self.ledger, self.now = cfg, snap, ledger, now
        self.spent = 0
        self.n_actions = 0
        self.squad = snap.squad()
        self.by_ptid = {e["ptid"]: e for e in self.squad}
        self.by_pid = {e["player"]["id"]: e for e in self.squad}
        self.xi = xi_set(snap.current_xi())
        self.projected = snap.projected_money
        self.market_bids = snap.my_bids()

    def refresh(self, snap):
        """Tras ventas/cláusulas en el mismo run: recalcular saldo y plantilla conservando los contadores del run."""
        self.s = snap
        self.squad = snap.squad()
        self.by_ptid = {e["ptid"]: e for e in self.squad}
        self.by_pid = {e["player"]["id"]: e for e in self.squad}
        self.xi = xi_set(snap.current_xi())
        self.projected = snap.projected_money
        self.market_bids = snap.my_bids()

    def check(self, a: Action) -> Verdict:
        c = self.cfg
        if c.kill_switch:
            return Verdict(False, "KILL_SWITCH")
        if a.group not in c.enabled_writes:
            return Verdict(False, f"grupo '{a.group}' no habilitado")
        if self.n_actions >= c.run.max_actions_per_run:
            return Verdict(False, "max_actions_per_run")
        if a.kind in SPENDING_KINDS:
            if not isinstance(a.amount, int) or a.amount <= 0:
                return Verdict(False, "importe inválido")
            if a.kind in ("bid", "modify_bid", "offer", "modify_offer", "clause_pay"):
                if a.market_value <= 0:
                    return Verdict(False, "sin valor de mercado")
                if a.amount >= a.market_value * ABSOLUTE_CAP:
                    return Verdict(False, f"precio >= {ABSOLUTE_CAP}x valor")
                cap = c.bids.hard_cap_ratio if a.kind != "clause_pay" else c.clauses.pay_cap_ratio
                if a.amount > a.market_value * cap + 1:
                    return Verdict(False, f"precio > {cap}x valor")
            if self.spent + a.amount > c.money.max_spend_per_run:
                return Verdict(False, "max_spend_per_run")
            floor = c.money.reserve if not c.money.allow_negative else -10**12
            if self.projected - self.spent - a.amount < floor:
                return Verdict(False, "saldo insuficiente")
        v = getattr(self, f"_check_{a.kind}", None)
        if v:
            r = v(a)
            if not r.ok:
                return r
        return Verdict(True)

    def commit(self, a: Action):
        """Llamar tras ejecutar (o simular) una acción para actualizar contadores del run."""
        self.n_actions += 1
        if a.kind in SPENDING_KINDS:
            self.spent += a.amount

    # ---------- reglas específicas ----------
    def _check_bid(self, a):
        if a.player_id in self.by_pid:
            return Verdict(False, "jugador propio")
        if a.player_id in self.s.recent_departures(int(self.cfg.bids.get("rebuy_veto_days", 0) or 0), self.now):
            return Verdict(False, "salió de mi plantilla hace poco (veto de recompra)")
        if self.ledger.bid_for(a.params.get("market_id")) or str(a.params.get("market_id")) in self.market_bids:
            return Verdict(False, "puja duplicada")
        if len(self.ledger.bids) >= self.cfg.money.max_pending_bids:
            return Verdict(False, "max_pending_bids")
        if len(self.squad) >= self.cfg.squad.max_size:
            return Verdict(False, "plantilla llena")
        return Verdict(True)

    _check_offer = _check_bid

    def _check_clause_pay(self, a):
        if a.player_id in self.by_pid:
            return Verdict(False, "jugador propio")
        if len(self.squad) >= self.cfg.squad.max_size:
            return Verdict(False, "plantilla llena")
        for r in self.s.rival_squads():
            if r["player"]["id"] == a.player_id:
                if r["lockedEnd"] and r["lockedEnd"] > self.now:
                    return Verdict(False, "cláusula bloqueada")
                if a.amount < r["buyoutClause"]:
                    return Verdict(False, "importe menor que la cláusula")
                return Verdict(True)
        return Verdict(False, "jugador no encontrado en plantillas rivales")

    def _check_clause_raise(self, a):
        if a.player_id not in self.by_pid:
            return Verdict(False, "no es jugador propio")
        if a.amount > self.cfg.clauses.raise_max_spend_per_run:
            return Verdict(False, "raise_max_spend_per_run")
        return Verdict(True)

    def _check_sell(self, a):
        return self._check_leaving(a, a.params.get("sale_price", 0))

    def _check_accept_offer(self, a):
        return self._check_leaving(a, a.params.get("offer_money", 0))

    def _check_leaving(self, a, price):
        e = self.by_pid.get(a.player_id)
        if not e:
            return Verdict(False, "no es jugador propio")
        if e["ptid"] in self.xi and price < e["player"]["marketValue"] * self.cfg.sales.starter_min_ratio:
            return Verdict(False, f"titular por debajo de {self.cfg.sales.starter_min_ratio}x valor")
        remaining = [x for x in self.squad if x["player"]["id"] != a.player_id]
        if len(remaining) < self.cfg.squad.min_size:
            return Verdict(False, "plantilla bajo mínimo")
        cnt = count_by_pos(remaining)
        pos = POS_NAMES.get(e["player"]["positionId"])
        if pos and cnt.get(pos, 0) < self.cfg.squad.min_per_pos.get(pos, 0):
            return Verdict(False, f"mínimo de {pos}")
        entries = [x for x in self.squad if x["player"]["positionId"] in (1, 2, 3, 4)]
        if not can_field_without(entries, e["ptid"], self.s.formations, spare=True):
            return Verdict(False, f"sin suplente de {pos}: no quedaría formación alineable con reserva")
        return Verdict(True)

    def _check_lineup(self, a):
        payload = a.params.get("payload") or {}
        ids = [payload.get("goalkeeper")] + list(payload.get("defender", [])) + list(payload.get("midfield", [])) + list(payload.get("striker", []))
        if len(ids) != 11 or len(set(ids)) != 11 or any(i is None for i in ids):
            return Verdict(False, "once incompleto o duplicado")
        if any(i not in self.by_ptid for i in ids):
            return Verdict(False, "jugador ajeno en el once")
        started = started_clubs(self.s, self.now)
        new_set, cur = set(ids), self.xi
        for ptid in (new_set ^ cur):
            if self.by_ptid.get(ptid, {}).get("player", {}).get("teamId") in started:
                return Verdict(False, "cambio con partido ya empezado")
        return Verdict(True)

"""Ejecuta acciones aprobadas por el guard: en dry-run solo registra; en vivo llama al cliente."""
from .client import ApiError
from .models import Action, Result


class Executor:
    def __init__(self, client, guard, ledger, dry_run: bool):
        self.c, self.g, self.ledger, self.dry_run = client, guard, ledger, dry_run

    def run(self, actions: list) -> list:
        results = []
        for a in actions:
            v = self.g.check(a)
            if not v.ok:
                results.append(Result(a, "BLOCKED", v.rule))
                continue
            if self.dry_run:
                self.g.commit(a)
                results.append(Result(a, "DRY"))
                continue
            try:
                detail = self._do(a)
                self.g.commit(a)
                results.append(Result(a, "OK", detail))
            except ApiError as e:
                if "429" in str(e):
                    results.append(Result(a, "ERROR", "429"))
                    raise
                results.append(Result(a, "ERROR", str(e)[:160]))
        return results

    def _do(self, a: Action) -> str:
        p, lid = a.params, a.params.get("league_id")
        if a.kind == "lineup":
            self.c.set_lineup(p["team_id"], p["payload"])
            return ""
        if a.kind in ("bid", "offer"):
            fn = self.c.bid if a.kind == "bid" else self.c.offer
            r = fn(lid, p["market_id"], p["money"])
            bid_id = (r or {}).get("id") if isinstance(r, dict) else None
            self.ledger.add_bid(p["market_id"], a.player_id, p["money"], bid_id, a.reason, kind=a.kind)
            return f"id={bid_id}"
        if a.kind == "modify_bid":
            self.c.modify_bid(lid, p["market_id"], p["bid_id"], p["money"])
            b = self.ledger.bid_for(p["market_id"])
            if b:
                b["money"] = p["money"]
            return ""
        if a.kind in ("cancel_bid", "cancel_offer"):
            fn = self.c.cancel_bid if a.kind == "cancel_bid" else self.c.cancel_offer
            fn(lid, p["market_id"], p["bid_id"])
            self.ledger.remove_bid(p["market_id"])
            return ""
        if a.kind == "sell":
            # se apunta ANTES de llamar: si la API responde y luego algo falla, el listado sigue siendo nuestro
            self.ledger.add_listing(None, a.player_id, p["sale_price"])
            r = self.c.sell(lid, p["player_team_id"], p["sale_price"])
            mid = (r or {}).get("id") if isinstance(r, dict) else None
            self.ledger.listings[-1]["market_id"] = str(mid) if mid else None
            return f"market_id={mid}"
        if a.kind == "withdraw":
            self.c.withdraw(lid, p["market_id"])
            return ""
        if a.kind == "accept_offer":
            self.c.accept_offer(lid, p["market_id"], p["offer_id"], p["offer_money"])
            self.ledger.handled_offers.append(p["offer_id"])
            return ""
        if a.kind == "reject_offer":
            self.c.reject_offer(lid, p["market_id"], p["offer_id"])
            self.ledger.handled_offers.append(p["offer_id"])
            return ""
        if a.kind == "clause_pay":
            self.c.pay_clause(lid, p["player_team_id"], p["amount"])
            return ""
        if a.kind == "daily_reward":
            r = self.c.claim_daily_reward(lid, p["team_id"], p.get("body"))
            return str(r)[:80] if r else ""
        if a.kind == "clause_raise":
            self.c.raise_clause(lid, p["player_team_id"], p["factor"], p["value_to_increase"])
            return ""
        raise ApiError(f"acción desconocida {a.kind}")

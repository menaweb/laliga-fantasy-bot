import pytest

from fantasy.guard import Guard
from fantasy.models import Action


def _bid(snap, mid="162148506", pid="9999", amount=1_000_000, mv=1_000_000):
    return Action("bid", pid, "X", amount, "t", {"league_id": snap.league_id, "market_id": mid, "money": amount}, market_value=mv)


def test_kill_switch_blocks_everything(snap, cfg, ledger, now):
    cfg["kill_switch"] = True
    assert Guard(cfg, snap, ledger, now).check(_bid(snap)).rule == "KILL_SWITCH"


def test_group_not_enabled(snap, cfg, ledger, now):
    cfg["enabled_writes"] = ("lineup",)
    assert "no habilitado" in Guard(cfg, snap, ledger, now).check(_bid(snap)).rule


def test_absolute_cap(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    assert not g.check(_bid(snap, amount=1_500_000, mv=1_000_000)).ok
    assert not g.check(_bid(snap, amount=1_495_000, mv=1_000_000)).ok      # > hard_cap_ratio 1.49
    assert g.check(_bid(snap, amount=1_400_000, mv=1_000_000)).ok


def test_budget_floor(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    assert g.check(_bid(snap, amount=snap.money + 1, mv=10**9)).rule == "saldo insuficiente"
    snap.investment = snap.money   # todo el dinero comprometido en pujas (teamInvestment)
    assert not Guard(cfg, snap, ledger, now).check(_bid(snap)).ok
    snap.investment = 0


def test_duplicate_detected_from_market(snap, cfg, ledger, now):
    snap.market[0]["bid"] = {"id": "1", "money": 100, "status": "pending"}
    assert Guard(cfg, snap, ledger, now).check(_bid(snap, mid=str(snap.market[0]["id"]))).rule == "puja duplicada"
    snap.market[0].pop("bid")


def test_max_spend_and_actions(snap, cfg, ledger, now):
    cfg["money"]["max_spend_per_run"] = 1_500_000
    g = Guard(cfg, snap, ledger, now)
    a = _bid(snap)
    assert g.check(a).ok
    g.commit(a)
    assert g.check(_bid(snap, mid="2")).rule == "max_spend_per_run"
    cfg["run"]["max_actions_per_run"] = 1
    assert Guard(cfg, snap, ledger, now).check(a).ok
    g2 = Guard(cfg, snap, ledger, now)
    g2.commit(a)
    assert g2.check(_bid(snap, mid="3")).rule == "max_actions_per_run"


def test_duplicate_and_own_player(snap, cfg, ledger, now):
    ledger.add_bid("162148506", "9999", 100)
    assert Guard(cfg, snap, ledger, now).check(_bid(snap)).rule == "puja duplicada"
    mine = snap.squad()[0]["player"]["id"]
    assert Guard(cfg, snap, ledger, now).check(_bid(snap, mid="7", pid=mine)).rule == "jugador propio"


def test_sell_rules(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    gk = next(e for e in snap.squad() if e["player"]["positionId"] == 1)
    a = Action("sell", gk["player"]["id"], "GK", 0, "", {"league_id": snap.league_id, "player_id": gk["player"]["id"], "sale_price": 10**9}, market_value=gk["player"]["marketValue"])
    assert g.check(a).rule == "mínimo de POR"
    starter_ptid = snap.current_xi()["defender"][0]
    st = next(e for e in snap.squad() if e["ptid"] == starter_ptid)
    cheap = Action("sell", st["player"]["id"], "DEF", 0, "", {"league_id": snap.league_id, "player_id": st["player"]["id"], "sale_price": int(st["player"]["marketValue"] * 0.5)}, market_value=st["player"]["marketValue"])
    assert "titular" in g.check(cheap).rule


def test_lineup_rules(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    xi = snap.current_xi()
    ok = Action("lineup", None, "L", 0, "", {"team_id": snap.team_id, "payload": {"goalkeeper": xi["goalkeeper"][0], "defender": xi["defender"], "midfield": xi["midfield"], "striker": xi["striker"], "tactical_formation": xi["formation"]}})
    assert g.check(ok).ok
    bad = Action("lineup", None, "L", 0, "", {"team_id": snap.team_id, "payload": {"goalkeeper": xi["goalkeeper"][0], "defender": xi["defender"][:3], "midfield": xi["midfield"], "striker": xi["striker"], "tactical_formation": [3, 4, 2]}})
    assert g.check(bad).rule == "once incompleto o duplicado"


def test_clause_pay_rules(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    r = next(x for x in snap.rival_squads() if x["buyoutClause"])
    a = Action("clause_pay", r["player"]["id"], "R", r["buyoutClause"], "", {"league_id": snap.league_id, "player_id": r["player"]["id"], "amount": r["buyoutClause"]}, market_value=r["player"]["marketValue"])
    v = g.check(a)
    assert v.ok or v.rule in ("saldo insuficiente", "cláusula bloqueada", "precio >= 1.5x valor", "precio > 1.5x valor")

from datetime import timedelta

from fantasy.guard import Guard
from fantasy.models import Action
from fantasy.strategy.clauses import plan_clause_raises
from fantasy.strategy.market import on_hold, plan_bids


def test_recent_signing_cannot_be_sold(snap, cfg, ledger, now):
    snap.manager_id = "11824032"
    xi = snap.current_xi()
    e = next(x for x in snap.squad() if x["player"]["positionId"] == 4 and x["ptid"] not in xi["striker"])
    snap.activity = [{"activityTypeId": 31, "user1Id": 11824032, "playerMasterId": int(e["player"]["id"]), "createdAt": (now - timedelta(days=3)).isoformat()}]
    assert on_hold(snap, ledger, cfg, e["player"]["id"], now)
    a = Action("sell", e["player"]["id"], "X", 0, "", {"league_id": snap.league_id, "player_team_id": e["ptid"], "sale_price": e["player"]["marketValue"] * 2}, market_value=e["player"]["marketValue"])
    assert "días" in Guard(cfg, snap, ledger, now).check(a).rule
    snap.activity = [dict(snap.activity[0], createdAt=(now - timedelta(days=20)).isoformat())]
    assert Guard(cfg, snap, ledger, now).check(a).ok


def test_clause_raise_only_for_valuable(snap, valuer, cfg, now):
    for a in plan_clause_raises(snap, valuer, cfg, now, budget=10**9):
        assert a.market_value >= cfg.clauses.raise_min_value


def test_quality_preference_orders_by_gain(snap, valuer, cfg, ledger, now):
    snap.money = 300_000_000
    acts, info = plan_bids(snap, valuer, cfg, ledger, now)
    gains = [float(a.reason.split("+")[1].split(" ")[0]) for a in acts if "HUECO" not in a.reason]
    assert gains == sorted(gains, reverse=True)

from datetime import timedelta

from fantasy.guard import Guard
from fantasy.models import Action
from fantasy.strategy.market import plan_bids


def test_departed_players_are_vetoed(snap, valuer, cfg, ledger, now):
    it = snap.market[0]
    pid = str(it["playerMaster"]["id"])
    snap.manager_id = "11824032"
    snap.activity = [{"activityTypeId": 1, "user1Id": 999, "user2Id": 11824032, "playerMasterId": int(pid),
                      "createdAt": (now - timedelta(days=2)).isoformat()}]
    assert pid in snap.recent_departures(21, now)
    assert pid not in snap.recent_departures(1, now)
    snap.money = 200_000_000
    acts, _ = plan_bids(snap, valuer, cfg, ledger, now)
    assert all(a.player_id != pid for a in acts)
    a = Action("bid", pid, "X", 1_000_000, "t", {"league_id": snap.league_id, "market_id": str(it["id"]), "money": 1_000_000}, market_value=1_000_000)
    assert "recompra" in Guard(cfg, snap, ledger, now).check(a).rule

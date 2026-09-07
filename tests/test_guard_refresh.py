from fantasy.guard import Guard
from fantasy.models import Action


def test_refresh_updates_projected_but_keeps_counters(snap, cfg, ledger, now):
    g = Guard(cfg, snap, ledger, now)
    a = Action("bid", "9999", "X", 1_000_000, "t", {"league_id": snap.league_id, "market_id": "m1", "money": 1_000_000}, market_value=1_000_000)
    assert g.check(a).ok
    g.commit(a)
    snap.money = snap.money + 19_000_000
    g.refresh(snap)
    assert g.projected == snap.money and g.spent == 1_000_000 and g.n_actions == 1
    big = Action("bid", "9998", "Y", 20_000_000, "t", {"league_id": snap.league_id, "market_id": "m2", "money": 20_000_000}, market_value=20_000_000)
    assert Guard(cfg, snap, ledger, now).check(big).ok

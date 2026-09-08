from datetime import timedelta

from fantasy.strategy.market import plan_bids


def _set_expirations(snap, when):
    for it in snap.market:
        it["expirationDate"] = when.isoformat()


def test_no_reserve_for_unfundable_or_expiring_targets(snap, valuer, cfg, ledger, now):
    snap.money = 1_000_000
    # todo el mercado caduca en 10h: nada financiable a tiempo
    _set_expirations(snap, now + timedelta(hours=10))
    _, info = plan_bids(snap, valuer, cfg, ledger, now)
    assert info["unaffordable_best"] is None
    # con 3 días de margen puede reservarse, pero nunca para algo que exija más que el banquillo + el peor titular
    _set_expirations(snap, now + timedelta(hours=72))
    _, info = plan_bids(snap, valuer, cfg, ledger, now)
    if info["unaffordable_best"]:
        squad_value = sum(e["player"]["marketValue"] for e in snap.squad())
        assert info["unaffordable_best"]["missing"] < squad_value
        assert info["unaffordable_best"]["hours_left"] > cfg.sales.fund_lead_hours

from datetime import timedelta

from fantasy.strategy.market import plan_sales, protected_ids


def test_protected_never_sold_to_fund_and_withdrawn_if_listed(snap, valuer, cfg, ledger, now):
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    prot = protected_ids(entries, valuer, cfg)
    oy = next(e for e in snap.squad() if e["player"]["nickname"] == "Oyarzabal")
    assert oy["player"]["id"] in prot
    fund = {"player": "X", "price": 90_000_000, "gain": 9.0, "missing": 50_000_000, "exp": 12.0, "hours_left": 60}
    acts = plan_sales(snap, valuer, cfg, ledger, now, fund=fund)
    assert not any(a.kind == "sell" and a.player_id in prot for a in acts)
    # si ya estuviera listado por nosotros, se retira
    for it in snap.team["players"]:
        if it["playerMaster"]["id"] == oy["player"]["id"]:
            it["playerMarket"] = {"id": "999", "salePrice": 1, "expirationDate": (now + timedelta(hours=70)).isoformat()}
    ledger.add_listing("999", oy["player"]["id"], 1)
    acts = plan_sales(snap, valuer, cfg, ledger, now, fund=None)
    assert any(a.kind == "withdraw" and a.player_id == oy["player"]["id"] for a in acts)


def test_manual_withdraw_vetoes_player(snap, cfg, ledger, now):
    pid = snap.squad()[3]["player"]["id"]
    ledger.add_listing("123", pid, 5)           # listado nuestro que ya no aparece en venta
    ledger.reconcile(snap, veto_days=7)
    assert ledger.is_vetoed(pid, now) and not ledger.listings

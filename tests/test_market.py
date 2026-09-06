from fantasy.strategy.market import bid_price, plan_bids, plan_offers, plan_sales


def test_bid_price_cap_and_overprice(cfg):
    assert bid_price(fair=10_000_000, mv=10_000_000, sale_price=10_000_000, markup=1.10, cfg=cfg) == 11_000_000
    assert bid_price(fair=10_000_000, mv=10_000_000, sale_price=16_000_000, markup=1.10, cfg=cfg) is None
    assert bid_price(fair=10_000_000, mv=10_000_000, sale_price=10_000_000, markup=1.30, cfg=cfg) == 13_000_000
    assert bid_price(fair=12_000_000, mv=10_000_000, sale_price=10_000_000, markup=1.30, cfg=cfg) <= 14_900_000


def test_plan_bids_respects_budget_and_no_duplicates(snap, valuer, cfg, ledger, now):
    acts, info = plan_bids(snap, valuer, cfg, ledger, now)
    assert sum(a.amount for a in acts) <= snap.money
    assert len({a.params["market_id"] for a in acts}) == len(acts)
    for a in acts:
        assert a.amount < a.market_value * 1.5
        assert a.player_id not in {e["player"]["id"] for e in snap.squad()}


def test_plan_bids_skips_already_bid(snap, valuer, cfg, ledger, now):
    acts, _ = plan_bids(snap, valuer, cfg, ledger, now)
    for a in acts:
        ledger.add_bid(a.params["market_id"], a.player_id, a.amount)
    again, _ = plan_bids(snap, valuer, cfg, ledger, now)
    assert not any(x.kind == "bid" and x.params["market_id"] in {a.params["market_id"] for a in acts} for x in again)


def test_offers_starter_not_ours_rejected(snap, valuer, cfg, ledger):
    acts = plan_offers(snap, valuer, cfg, ledger)
    assert acts and all(a.kind in ("accept_offer", "reject_offer") for a in acts)
    szc = [a for a in acts if a.player_name == "Szczesny"]
    assert szc and szc[0].kind == "reject_offer"


def test_fund_sale_when_upgrade_unaffordable(snap, valuer, cfg, ledger, now):
    _, info = plan_bids(snap, valuer, cfg, ledger, now)
    fund = info["unaffordable_best"]
    if fund:
        acts = plan_sales(snap, valuer, cfg, ledger, now, fund=fund)
        sells = [a for a in acts if a.kind == "sell"]
        assert len(sells) == 1 and sells[0].market_value >= fund["missing"]
        assert valuer.exp(next(e["player"] for e in snap.squad() if e["player"]["id"] == sells[0].player_id)) < fund["exp"]

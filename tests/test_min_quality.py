from fantasy.strategy.market import plan_bids
from fantasy.strategy.clauses import plan_clause_pays


def test_signings_meet_quality_floor(snap, valuer, cfg, ledger, now):
    snap.money = 300_000_000
    acts, info = plan_bids(snap, valuer, cfg, ledger, now)
    for a in acts:
        if a.kind in ("bid", "offer"):
            floor = cfg.bids.min_exp_emergency if any(k in a.reason for k in ("HUECO",)) and a.reason.split()[1] in info["critical"] else cfg.bids.min_exp_signing
            assert valuer.exp(snap.players[a.player_id]) >= min(floor, cfg.bids.min_exp_signing)
    for a in plan_clause_pays(snap, valuer, cfg, now, budget=10**9):
        assert valuer.exp(snap.players[a.player_id]) >= cfg.bids.min_exp_signing


def test_low_quality_active_bid_gets_cancelled(snap, valuer, cfg, ledger, now):
    it = min(snap.market, key=lambda i: float(i["playerMaster"].get("averagePoints") or 0))
    pid = str(it["playerMaster"]["id"])
    if valuer.exp(snap.players[pid]) < cfg.bids.min_exp_signing:
        ledger.add_bid(str(it["id"]), pid, 1_000_000, bid_id="b1")
        acts, _ = plan_bids(snap, valuer, cfg, ledger, now)
        assert any(a.kind == "cancel_bid" and a.player_id == pid for a in acts)

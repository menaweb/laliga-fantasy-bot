from fantasy.strategy.market import plan_bids
from fantasy.strategy.squad import gaps
from fantasy.strategy.value import Valuer


def test_emergency_without_goalkeeper_buys_any_available_gk(snap, cfg, ledger, now):
    # quitar al único portero de la fixture -> emergencia POR
    snap.team["players"] = [it for it in snap.team["players"] if int(it["playerMaster"]["positionId"]) != 1]
    v = Valuer(snap, None, None, cfg, "2026-09-06")
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    assert "POR" in gaps(entries, v, cfg)
    snap.money = 60_000_000
    acts, info = plan_bids(snap, v, cfg, ledger, now)
    gk_bids = [a for a in acts if a.kind in ("bid", "offer") and snap.players[a.player_id]["positionId"] == 1]
    assert gk_bids, "en emergencia debe pujar por algún portero aunque no llegue al mínimo de calidad"
    assert all(v.exp(snap.players[a.player_id]) >= cfg.bids.min_exp_emergency for a in gk_bids)
    assert "HUECO POR" in gk_bids[0].reason and gk_bids[0] is acts[0]   # la emergencia va primero en la cola

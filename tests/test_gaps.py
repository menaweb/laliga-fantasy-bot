from fantasy.strategy.squad import best_xi, gaps
from fantasy.strategy.value import Valuer


def test_weak_goalkeeper_is_critical(snap, cfg):
    gk = next(e["player"] for e in snap.squad() if e["player"]["positionId"] == 1)
    v = Valuer(snap, None, {gk["id"]: {"status": "bench", "pct": 0}}, cfg, "2026-09-06")
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    xi = best_xi(entries, v, snap.formations)
    assert "POR" in gaps(entries, v, cfg, xi)
    assert gaps(entries, v, cfg) == []          # sin once no hay regla de titular flojo


def test_weak_gap_does_not_buy_worse_players(snap, cfg, ledger, now):
    from datetime import datetime, timezone
    from fantasy.strategy.market import plan_bids
    gk = next(e["player"] for e in snap.squad() if e["player"]["positionId"] == 1)
    v = Valuer(snap, None, {gk["id"]: {"status": "bench", "pct": 0}}, cfg, "2026-09-06")
    snap.money = 40_000_000
    acts, info = plan_bids(snap, v, cfg, ledger, now)
    assert "POR" in info["critical"]
    if any("HUECO" in a.reason for a in acts):   # si hay candidatos de hueco, van primero
        assert "HUECO" in acts[0].reason
    for a in acts:
        assert "+-" not in a.reason and v.exp(snap.players[a.player_id]) >= cfg.squad.weak_starter_exp

from fantasy.strategy.squad import best_xi, gaps
from fantasy.strategy.value import Valuer


def test_weak_goalkeeper_is_critical(snap, cfg):
    gk = next(e["player"] for e in snap.squad() if e["player"]["positionId"] == 1)
    v = Valuer(snap, None, {gk["id"]: {"status": "bench", "pct": 0}}, cfg, "2026-09-06")
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    xi = best_xi(entries, v, snap.formations)
    assert "POR" in gaps(entries, v, cfg, xi)
    assert gaps(entries, v, cfg) == []          # sin once no hay regla de titular flojo

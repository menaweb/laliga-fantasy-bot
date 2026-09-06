from fantasy.strategy.value import Valuer


def test_injured_is_zero(snap, cfg, valuer):
    p = dict(next(iter(snap.players.values())), playerStatus="injured", teamId="16")
    assert valuer.exp(p) == 0.0


def test_no_match_is_zero(snap, cfg, valuer):
    p = dict(next(iter(snap.players.values())), teamId="999", playerStatus="ok")
    assert valuer.exp(p) == 0.0


def test_fair_equals_mv_without_history(snap, valuer):
    p = next(iter(snap.players.values()))
    assert valuer.fair(p) == p["marketValue"]


def test_probable_scales(snap, cfg):
    p = next(e["player"] for e in snap.squad() if e["player"]["nickname"] == "Oyarzabal")
    v_none = Valuer(snap, None, None, cfg, "2026-09-06").exp(p)
    v_bench = Valuer(snap, None, {p["id"]: {"status": "bench", "pct": 0}}, cfg, "2026-09-06").exp(p)
    v_inj = Valuer(snap, None, {p["id"]: {"status": "injured", "pct": 0}}, cfg, "2026-09-06").exp(p)
    assert v_inj == 0 and 0 < v_bench < v_none
    assert abs(v_bench / v_none - cfg.lineup.probable_min_factor) < 1e-6


def test_prior_is_bounded(snap, cfg, valuer):
    p = dict(next(iter(snap.players.values())), marketValue=200_000_000, points=0, averagePoints=0, lastSeasonPoints=0, weekPoints=[])
    base, _ = valuer.base_points(p)
    assert base <= 8.0

from datetime import datetime, timezone

from fantasy.strategy.lineup import plan_lineup, started_clubs
from fantasy.strategy.squad import best_xi, xi_set, parse_formation


def test_parse_formation():
    assert parse_formation("4,4,2") == {1: 1, 2: 4, 3: 4, 4: 2}


def test_best_xi_has_11_and_valid_formation(snap, valuer):
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    b = best_xi(entries, valuer, snap.formations)
    assert len(xi_set(b)) == 11 and ",".join(map(str, b["formation"])) in snap.formations


def test_no_change_when_all_started(snap, valuer, cfg):
    # domingo 22:30 local: la mayoría ha jugado -> el once actual está bloqueado casi entero
    a, why = plan_lineup(snap, valuer, cfg, datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc))
    if a:  # si propone algo, solo puede tocar clubes que no han empezado
        started = started_clubs(snap, datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc))
        by_ptid = {e["ptid"]: e for e in snap.squad()}
        changed = xi_set({k: v if isinstance(v, list) else [v] for k, v in a.params["payload"].items() if k != "tactical_formation"}) ^ xi_set(snap.current_xi())
        assert all(by_ptid[p]["player"]["teamId"] not in started for p in changed)


def test_change_proposed_before_week_starts(snap, valuer, cfg):
    snap.week = dict(snap.week, isLive=False)
    a, why = plan_lineup(snap, valuer, cfg, datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc))
    assert a is not None and a.kind == "lineup"
    p = a.params["payload"]
    assert len(p["defender"]) + len(p["midfield"]) + len(p["striker"]) == 10 and p["goalkeeper"]
    assert p["tactical_formation"] == [len(p["defender"]), len(p["midfield"]), len(p["striker"])]

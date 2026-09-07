from datetime import timedelta

from fantasy.strategy.clauses import plan_clause_pays, plan_clause_raises, clause_open


def test_clause_open(now):
    assert clause_open(None, now) and clause_open(now - timedelta(hours=1), now) and not clause_open(now + timedelta(hours=1), now)


def test_pays_respect_cap_lock_and_budget(snap, valuer, cfg, now):
    acts = plan_clause_pays(snap, valuer, cfg, now, budget=10**9)
    rivals = {r["player"]["id"]: r for r in snap.rival_squads()}
    for a in acts:
        r = rivals[a.player_id]
        assert a.amount == r["buyoutClause"] and a.amount <= a.market_value * 1.5
        assert a.params["player_team_id"] == r["ptid"]
        assert clause_open(r["lockedEnd"], now)
    assert plan_clause_pays(snap, valuer, cfg, now, budget=0) == []


def test_raise_math_and_budget(snap, valuer, cfg, now):
    acts = plan_clause_raises(snap, valuer, cfg, now, budget=snap.money)
    for a in acts:
        assert a.params["value_to_increase"] == a.amount * 2 and a.amount <= cfg.clauses.raise_max_spend_per_run
        assert a.params["player_team_id"] in {e["ptid"] for e in snap.squad()}
    assert sum(a.amount for a in acts) <= snap.money

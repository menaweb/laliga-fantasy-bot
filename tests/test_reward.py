from fantasy.guard import Guard
from fantasy.models import Action


def _reward(snap):
    return Action("daily_reward", None, "Recompensa diaria", 0, "test", {"league_id": snap.league_id, "team_id": snap.team_id})


def test_reward_gated_by_group(snap, cfg, ledger, now):
    cfg["enabled_writes"] = ("lineup",)
    assert not Guard(cfg, snap, ledger, now).check(_reward(snap)).ok
    cfg["enabled_writes"] = ("reward",)
    assert Guard(cfg, snap, ledger, now).check(_reward(snap)).ok


def test_reward_group_parsed(monkeypatch):
    import os
    from fantasy.config import load_config
    monkeypatch.setenv("ENABLED_WRITES", "lineup,market,clauses,reward")
    assert "reward" in load_config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")).enabled_writes

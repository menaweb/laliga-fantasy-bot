import os
import pytest
import yaml

from fantasy.config import load_config, validate, Section, ABSOLUTE_CAP
from tests.conftest import ROOT


def _cfg_with(tmp_path, **over):
    raw = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    for k, v in over.items():
        sec, key = k.split(".")
        raw[sec][key] = v
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(raw))
    return str(p)


def test_loads_default():
    c = load_config(os.path.join(ROOT, "config.yaml"))
    assert c.bids.hard_cap_ratio < ABSOLUTE_CAP and c.league_id


def test_rejects_cap_at_or_above_1_5(tmp_path):
    with pytest.raises(ValueError):
        load_config(_cfg_with(tmp_path, **{"bids.hard_cap_ratio": 1.5}))
    with pytest.raises(ValueError):
        load_config(_cfg_with(tmp_path, **{"clauses.pay_cap_ratio": 1.6}))


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("KILL_SWITCH", "true")
    monkeypatch.setenv("ENABLED_WRITES", "lineup, bogus ,market")
    c = load_config(os.path.join(ROOT, "config.yaml"))
    assert c.dry_run is False and c.kill_switch is True and c.enabled_writes == ("lineup", "market")

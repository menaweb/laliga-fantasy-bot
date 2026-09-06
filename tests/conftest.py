import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("ENABLED_WRITES", "lineup,market,clauses")
os.environ.setdefault("DRY_RUN", "true")

from fantasy.config import load_config            # noqa: E402
from fantasy.state import Ledger                  # noqa: E402
from fantasy.strategy.value import Valuer         # noqa: E402
from tests.helpers import snapshot_from_dir       # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ROOT = os.path.dirname(os.path.dirname(__file__))
NOW = datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc)   # domingo noche, J4 en juego


@pytest.fixture
def cfg():
    return load_config(os.path.join(ROOT, "config.yaml"))


@pytest.fixture
def snap():
    return snapshot_from_dir(FIX)


@pytest.fixture
def valuer(snap, cfg):
    return Valuer(snap, None, None, cfg, "2026-09-06")


@pytest.fixture
def ledger(tmp_path):
    return Ledger(str(tmp_path))


@pytest.fixture
def now():
    return NOW

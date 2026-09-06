"""Run completo en dry-run con un cliente falso: N decisiones, 0 escrituras."""
import os

from fantasy.executor import Executor
from fantasy.guard import Guard
from fantasy.strategy.market import plan_bids, plan_offers, plan_sales
from fantasy.strategy.clauses import plan_clause_raises
from fantasy.notify import format_run


class FakeClient:
    def __getattr__(self, name):
        raise AssertionError(f"escritura inesperada en dry-run: {name}")


def test_dry_run_never_calls_client(snap, valuer, cfg, ledger, now):
    acts = plan_offers(snap, valuer, cfg, ledger)
    bids, info = plan_bids(snap, valuer, cfg, ledger, now)
    acts += bids + plan_sales(snap, valuer, cfg, ledger, now, fund=info["unaffordable_best"]) + plan_clause_raises(snap, valuer, cfg, now, snap.money)
    res = Executor(FakeClient(), Guard(cfg, snap, ledger, now), ledger, dry_run=True).run(acts)
    assert res and all(r.status in ("DRY", "BLOCKED") for r in res)
    text = format_run({"week": 4, "live": True, "mode": "DRY", "money": snap.money, "projected": info["projected"], "results": res, "notes": [], "errors": [], "position": 9, "points": 72})
    assert "Bearer" not in text and "DRY" in text


def test_secrets_are_gitignored():
    gi = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")).read().split()
    assert ".env" in gi and "tokens.json" in gi and "data/" in gi

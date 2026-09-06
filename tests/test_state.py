import json

from fantasy.state import Ledger, ValueHistory


def test_value_history_once_per_day_and_trend(tmp_path, snap):
    vh = ValueHistory(str(tmp_path))
    assert vh.record_today(snap.players, "2026-09-01") and not vh.record_today(snap.players, "2026-09-01")
    pid = next(iter(snap.players))
    later = {pid: dict(snap.players[pid], marketValue=int(snap.players[pid]["marketValue"] * 1.1))}
    vh.record_today(later, "2026-09-06")
    assert abs(vh.trend(pid, "2026-09-06") - 0.1) < 1e-6
    assert vh.trend("nope", "2026-09-06") is None


def test_ledger_reconcile_and_persist(tmp_path, snap):
    l = Ledger(str(tmp_path))
    l.add_bid("162148506", "3095", 900000)      # existe en el mercado de la fixture
    l.add_bid("000", "1", 100)                  # ya no existe
    l.reconcile(snap)
    assert [b["market_id"] for b in l.bids] == ["162148506"] and l.pending_bid_total() == 900000
    l.save()
    assert json.load(open(tmp_path / "ledger.json"))["bids"][0]["player_id"] == "3095"

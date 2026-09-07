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
    snap.market[0]["bid"] = {"id": "26578528", "money": 900000, "status": "pending"}   # mi puja según la API
    l.add_bid("162148506", "3095", 850000)      # en el ledger con otro importe y sin bid_id
    l.add_bid("000", "1", 100)                  # ya no existe en el mercado
    l.reconcile(snap)
    assert [b["market_id"] for b in l.bids] == ["162148506"] and l.pending_bid_total() == 900000 and l.bids[0]["bid_id"] == "26578528"
    l2 = Ledger(str(tmp_path / "x"))
    l2.reconcile(snap)                          # ledger vacío: adopta la puja detectada en el mercado
    assert l2.bids and l2.bids[0]["reason"] == "detectada en el mercado"
    snap.market[0].pop("bid")
    l.save()
    assert json.load(open(tmp_path / "ledger.json"))["bids"][0]["player_id"] == "3095"


def test_projected_money_uses_investment(snap):
    snap.investment = 468827
    assert snap.projected_money == snap.money - 468827

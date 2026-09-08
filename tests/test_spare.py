from fantasy.guard import Guard
from fantasy.models import Action
from fantasy.strategy.squad import can_field_without


def _sell(snap, e, price=None):
    return Action("sell", e["player"]["id"], e["player"]["nickname"], 0, "", {"league_id": snap.league_id, "player_team_id": e["ptid"],
                  "sale_price": price or e["player"]["marketValue"] * 2}, market_value=e["player"]["marketValue"])


def test_cannot_sell_down_to_exact_formation_needs(snap, cfg, ledger, now):
    # fixture: 1 POR, 5 DEF, 4 MED, 3 DEL
    entries = [e for e in snap.squad() if e["player"]["positionId"] < 5]
    gk = next(e for e in entries if e["player"]["positionId"] == 1)
    mid = next(e for e in entries if e["player"]["positionId"] == 3)
    fwd = next(e for e in entries if e["player"]["positionId"] == 4)
    assert not can_field_without(entries, gk["ptid"], snap.formations)
    assert not can_field_without(entries, mid["ptid"], snap.formations)   # 3 MED: ninguna formación deja suplente
    assert can_field_without(entries, fwd["ptid"], snap.formations)       # 2 DEL: 5-4-1 deja uno de reserva
    g = Guard(cfg, snap, ledger, now)
    assert "suplente" in g.check(_sell(snap, mid)).rule or "mínimo" in g.check(_sell(snap, mid)).rule
    assert g.check(_sell(snap, fwd)).ok

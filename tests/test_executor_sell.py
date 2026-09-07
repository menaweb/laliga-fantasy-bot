from fantasy.executor import Executor
from fantasy.guard import Guard
from fantasy.models import Action


class FakeClient:
    def __init__(self):
        self.calls = []

    def sell(self, lid, ptid, price):
        self.calls.append(("sell", lid, ptid, price))
        return {"id": "30841645", "salePrice": price}


def test_live_sell_records_listing(snap, cfg, ledger, now):
    cfg["dry_run"] = False
    e = next(x for x in snap.squad() if x["player"]["nickname"] == "D. Villares")
    a = Action("sell", e["player"]["id"], "D. Villares", 0, "t",
               {"league_id": snap.league_id, "player_team_id": e["ptid"], "sale_price": e["player"]["marketValue"] * 2},
               market_value=e["player"]["marketValue"])
    fc = FakeClient()
    res = Executor(fc, Guard(cfg, snap, ledger, now), ledger, dry_run=False).run([a])
    assert res[0].status == "OK" and fc.calls[0][2] == e["ptid"]
    assert ledger.listings[-1]["market_id"] == "30841645" and ledger.listings[-1]["player_id"] == e["player"]["id"]

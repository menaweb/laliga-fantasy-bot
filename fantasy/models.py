"""Tipos ligeros compartidos por estrategia, guard y executor."""
from dataclasses import dataclass, field

# kind -> grupo de escritura (ENABLED_WRITES)
KIND_GROUP = {
    "lineup": "lineup",
    "bid": "market", "modify_bid": "market", "cancel_bid": "market",
    "offer": "market", "modify_offer": "market", "cancel_offer": "market",
    "sell": "market", "withdraw": "market", "accept_offer": "market", "reject_offer": "market",
    "clause_pay": "clauses", "clause_raise": "clauses",
    "daily_reward": "reward",
}
# kinds que gastan dinero de verdad (para presupuesto del run)
SPENDING_KINDS = {"bid", "modify_bid", "offer", "modify_offer", "clause_pay", "clause_raise"}


@dataclass
class Action:
    kind: str
    player_id: str | None
    player_name: str
    amount: int = 0                 # importe que se compromete (puja, cláusula, coste de subida)
    reason: str = ""
    params: dict = field(default_factory=dict)  # ids que necesita el cliente
    market_value: int = 0           # valor de mercado del jugador implicado (para el guard)

    @property
    def group(self) -> str:
        return KIND_GROUP[self.kind]

    def describe(self) -> str:
        amt = f" · {self.amount:,} €".replace(",", ".") if self.amount else ""
        return f"[{self.kind}] {self.player_name}{amt} · {self.reason}"


@dataclass
class Result:
    action: Action
    status: str          # DRY | OK | BLOCKED | ERROR
    detail: str = ""

    def line(self) -> str:
        tail = f" -> {self.status}" + (f" ({self.detail})" if self.detail else "")
        return self.action.describe() + tail


def norm_player(pm: dict) -> dict:
    """Normaliza un playerMaster (de /players, plantilla, mercado o lineup): la API mezcla str e int."""
    def _i(v, d=0):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return d
    team_id = pm.get("teamId")
    if team_id is None and isinstance(pm.get("team"), dict):
        team_id = pm["team"].get("id")
    return {
        "id": str(pm.get("id")),
        "nickname": pm.get("nickname") or pm.get("name") or "?",
        "name": pm.get("name") or pm.get("nickname") or "?",
        "positionId": _i(pm.get("positionId")),
        "teamId": str(team_id) if team_id is not None else None,
        "marketValue": _i(pm.get("marketValue")),
        "points": _i(pm.get("points")),
        "averagePoints": float(pm.get("averagePoints") or 0),
        "playerStatus": pm.get("playerStatus") or "unknown",
        "lastSeasonPoints": _i(pm.get("lastSeasonPoints")),
        "weekPoints": pm.get("weekPoints") or [],
    }

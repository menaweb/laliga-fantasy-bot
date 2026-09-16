"""Clausulazos a rivales y subida de cláusulas propias."""
from datetime import datetime

from ..config import ABSOLUTE_CAP, POS_NAMES
from ..models import Action
from .squad import best_xi, weakest_in_xi, xi_set

RAISE_FACTOR = 2  # pagas X y la cláusula sube 2X (app oficial)


def clause_open(locked_end, now: datetime) -> bool:
    return locked_end is None or locked_end <= now


def plan_clause_pays(snap, valuer, cfg, now: datetime, budget: int) -> list:
    actions = []
    entries = [e for e in snap.squad() if e["player"]["positionId"] in (1, 2, 3, 4)]
    xi = best_xi(entries, valuer, snap.formations or ["4,4,2"]) or snap.current_xi()
    room = cfg.squad.max_size - len(snap.squad())
    departed = snap.recent_departures(int(cfg.bids.get("rebuy_veto_days", 0) or 0), now)
    cands = []
    for r in snap.rival_squads():
        p = r["player"]
        if p["positionId"] not in (1, 2, 3, 4) or valuer.availability(p) <= 0 or r["onSale"] or p["id"] in departed:
            continue
        cl = r["buyoutClause"]
        if not cl or cl > p["marketValue"] * min(cfg.clauses.pay_cap_ratio, ABSOLUTE_CAP):
            continue
        if not clause_open(r["lockedEnd"], now):
            continue
        weakest = weakest_in_xi(entries, xi, valuer, p["positionId"])
        g = valuer.exp(p) - (valuer.exp(weakest["player"]) if weakest else 0.0)
        if g < cfg.clauses.pay_min_gain_points:
            continue
        cands.append((g / cl * 1e6, g, cl, r))
    cands.sort(key=lambda t: -t[0])
    spent, n = 0, 0
    for score, g, cl, r in cands:
        if n >= cfg.clauses.max_pays_per_run or room - n <= 0:
            break
        if budget - spent - cl < cfg.money.reserve:
            continue
        p = r["player"]
        actions.append(Action("clause_pay", p["id"], p["nickname"], cl,
                              f"clausulazo a {r['manager']} · cláusula {cl:,} = {cl / p['marketValue']:.2f}×valor · +{g:.1f} pts al once".replace(",", "."),
                              {"league_id": snap.league_id, "player_team_id": r["ptid"], "amount": cl}, market_value=p["marketValue"]))
        spent += cl
        n += 1
    return actions


def plan_clause_raises(snap, valuer, cfg, now: datetime, budget: int) -> list:
    """Sube la cláusula de mis mejores jugadores cuando está barata respecto a su valor."""
    actions = []
    entries = [e for e in snap.squad() if e["player"]["positionId"] in (1, 2, 3, 4)]
    top = sorted(entries, key=lambda e: -valuer.exp(e["player"]))[: cfg.clauses.raise_top_n]
    min_value = int(cfg.clauses.get("raise_min_value", 0) or 0)
    spent = 0
    for e in top:
        p, cl = e["player"], e["buyoutClause"]
        if not cl or not p["marketValue"] or e["isShielded"] or p["marketValue"] < min_value:
            continue
        ratio = cl / p["marketValue"]
        if ratio >= cfg.clauses.raise_when_ratio_below:
            continue
        target = int(p["marketValue"] * cfg.clauses.raise_target_ratio)
        increase = target - cl
        cost = increase // RAISE_FACTOR
        remaining = min(cfg.clauses.raise_max_spend_per_run - spent, budget - spent - cfg.money.reserve)
        if cost > remaining:
            cost = max(0, remaining)
            increase = cost * RAISE_FACTOR
        if cost < 500_000:
            continue
        actions.append(Action("clause_raise", p["id"], p["nickname"], cost,
                              f"cláusula {cl:,} = {ratio:.2f}×valor -> +{increase:,} (coste {cost:,})".replace(",", "."),
                              {"league_id": snap.league_id, "player_team_id": e["ptid"], "factor": RAISE_FACTOR, "value_to_increase": increase},
                              market_value=p["marketValue"]))
        spent += cost
    return actions

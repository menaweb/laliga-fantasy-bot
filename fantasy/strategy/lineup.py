"""Decide la alineación: mejor once por puntos esperados respetando partidos ya empezados."""
from datetime import datetime

from ..models import Action
from ..state import parse_dt
from .squad import best_xi, xi_set


def started_clubs(snap, now: datetime) -> set:
    """Clubes cuyo partido de la jornada en curso ya ha empezado (solo si la jornada está live)."""
    if not snap.is_live:
        return set()
    out = set()
    for m in snap.matches(snap.week_number):
        dt = parse_dt(m.get("matchDate"))
        if (dt and dt <= now) or (m.get("matchState") not in (None, 1)):
            out.add(str(m.get("localId")))
            out.add(str(m.get("visitorId")))
    return out


def plan_lineup(snap, valuer, cfg, now: datetime) -> tuple[Action | None, str]:
    entries = [e for e in snap.squad() if e["player"]["positionId"] in (1, 2, 3, 4)]
    current = snap.current_xi()
    cur_set = xi_set(current)
    started = started_clubs(snap, now)
    locked_in = {e["ptid"] for e in entries if e["ptid"] in cur_set and e["player"]["teamId"] in started}
    excluded = {e["ptid"] for e in entries if e["ptid"] not in cur_set and e["player"]["teamId"] in started}

    best = best_xi(entries, valuer, snap.formations or ["4,4,2"], locked_in=locked_in, excluded=excluded)
    if not best:
        return None, "no se puede completar el once con los jugadores no bloqueados (jornada en juego)" if started else "no hay once válido con la plantilla actual"
    cur_total = sum(valuer.exp(e["player"]) for e in entries if e["ptid"] in cur_set)
    unavailable = [e for e in entries if e["ptid"] in cur_set and valuer.availability(e["player"]) <= 0]
    same = xi_set(best) == cur_set and list(best["formation"]) == list(current.get("formation") or [])
    if same:
        return None, f"once ya óptimo ({best['total']:.1f} pts esp)"
    gain = best["total"] - cur_total
    if gain < cfg.lineup.min_improvement and not unavailable and len(cur_set) == 11:
        return None, f"cambio no compensa (+{gain:.1f} pts)"
    payload = {
        "goalkeeper": best["goalkeeper"][0],
        "defender": best["defender"], "midfield": best["midfield"], "striker": best["striker"],
        "tactical_formation": best["formation"],
    }
    names = {e["ptid"]: e["player"]["nickname"] for e in entries}
    ins = [names[p] for p in xi_set(best) - cur_set]
    outs = [names.get(p, p) for p in cur_set - xi_set(best)]
    reason = (f"{'-'.join(map(str, best['formation']))} {best['total']:.1f} pts esp (+{gain:.1f})"
              + (f" · entran {', '.join(ins)}" if ins else "") + (f" · salen {', '.join(outs)}" if outs else "")
              + (f" · no disponibles: {', '.join(e['player']['nickname'] for e in unavailable)}" if unavailable else ""))
    return Action("lineup", None, "Alineación", 0, reason, {"team_id": snap.team_id, "payload": payload}), reason

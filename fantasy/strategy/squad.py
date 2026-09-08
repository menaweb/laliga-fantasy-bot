"""Once ideal, huecos posicionales y sobrantes de la plantilla."""
from itertools import combinations

from ..config import POS_NAMES

LINES = {1: "goalkeeper", 2: "defender", 3: "midfield", 4: "striker"}


def parse_formation(f) -> dict:
    """'4,4,2' o [4,4,2] -> {1:1, 2:4, 3:4, 4:2}"""
    parts = [int(x) for x in (f.split(",") if isinstance(f, str) else f)]
    return {1: 1, 2: parts[0], 3: parts[1], 4: parts[2]}


def best_xi(entries: list, valuer, formations: list, locked_in: set = (), excluded: set = ()) -> dict | None:
    """
    entries: [{ptid, player}] de la plantilla. Devuelve la mejor formación y once por puntos esperados.
    locked_in: ptids que deben seguir en el once (su partido ya empezó). excluded: ptids que no pueden entrar.
    """
    by_pos = {1: [], 2: [], 3: [], 4: []}
    for e in entries:
        pos = e["player"]["positionId"]
        if pos in by_pos and e["ptid"] not in excluded:
            by_pos[pos].append(e)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda e: -valuer.exp(e["player"]))
    best = None
    for f in formations:
        need = parse_formation(f)
        lines, total, ok = {}, 0.0, True
        for pos, n in need.items():
            cands = by_pos[pos]
            must = [e for e in cands if e["ptid"] in locked_in]
            if len(must) > n or len(cands) < n:
                ok = False
                break
            rest = [e for e in cands if e["ptid"] not in locked_in]
            chosen = must + rest[: n - len(must)]
            lines[LINES[pos]] = [e["ptid"] for e in chosen]
            total += sum(valuer.exp(e["player"]) for e in chosen)
        if ok and (best is None or total > best["total"]):
            best = {"formation": [need[2], need[3], need[4]], "total": total, **lines}
    return best


def xi_set(xi: dict) -> set:
    return set(xi.get("goalkeeper", [])) | set(xi.get("defender", [])) | set(xi.get("midfield", [])) | set(xi.get("striker", []))


def count_by_pos(entries: list, available_only=False, valuer=None) -> dict:
    out = {"POR": 0, "DEF": 0, "MED": 0, "DEL": 0, "ENT": 0}
    for e in entries:
        if available_only and valuer and valuer.availability(e["player"]) <= 0:
            continue
        out[POS_NAMES.get(e["player"]["positionId"], "ENT")] += 1
    return out


def gaps(entries: list, valuer, cfg, xi: dict | None = None) -> list:
    """Posiciones críticas: no se alcanza el mínimo con disponibles, o un titular del once es muy flojo
    (p.ej. portero suplente en su club)."""
    avail = count_by_pos(entries, available_only=True, valuer=valuer)
    out = [pos for pos, n in cfg.squad.min_per_pos.items() if avail.get(pos, 0) < n]
    if xi:
        weak = float(cfg.squad.get("weak_starter_exp", 0) or 0)
        in_xi = xi_set(xi)
        for e in entries:
            pos = POS_NAMES.get(e["player"]["positionId"])
            if e["ptid"] in in_xi and pos and pos not in out and valuer.exp(e["player"]) < weak:
                out.append(pos)
    return out


UNAVAILABLE = {"injured", "suspended", "out_of_league"}


def can_field_without(entries: list, ptid: str, formations: list, spare: bool = True) -> bool:
    """¿Tras quitar a `ptid` queda alguna formación alineable con jugadores no lesionados/sancionados,
    y (si spare) con al menos un suplente en la posición del que se va?"""
    gone = next((e for e in entries if e["ptid"] == ptid), None)
    remaining = [e for e in entries if e["ptid"] != ptid and e["player"].get("playerStatus") not in UNAVAILABLE]
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for e in remaining:
        if e["player"]["positionId"] in counts:
            counts[e["player"]["positionId"]] += 1
    gone_pos = gone["player"]["positionId"] if gone else None
    for f in formations or ["4,4,2"]:
        need = parse_formation(f)
        ok = all(counts[pos] >= n for pos, n in need.items())
        if ok and spare and gone_pos in need:
            ok = counts[gone_pos] >= need[gone_pos] + 1
        if ok:
            return True
    return False


def weakest_in_xi(entries: list, xi: dict, valuer, position_id: int):
    """Titular más flojo de esa posición (candidato a ser desplazado por un fichaje)."""
    ids = set(xi.get(LINES[position_id], []))
    cands = [e for e in entries if e["ptid"] in ids]
    return min(cands, key=lambda e: valuer.exp(e["player"]), default=None)


def surplus(entries: list, xi: dict, valuer, keep_bench_per_pos: int = 1) -> list:
    """Jugadores fuera del once y fuera del primer suplente de su posición."""
    in_xi = xi_set(xi)
    out = []
    for pos in (1, 2, 3, 4):
        bench = [e for e in entries if e["player"]["positionId"] == pos and e["ptid"] not in in_xi]
        bench.sort(key=lambda e: -valuer.exp(e["player"]))
        out += bench[keep_bench_per_pos:]
    return out

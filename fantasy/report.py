"""
Genera el informe semanal (Markdown) con plantilla, presupuesto, mercado y
señales de valor. Está pensado para pegarlo tal cual en el chat con Claude.

Reglas incorporadas (las de Rafa):
  - Puja de referencia = valor de mercado x 1.10
  - Sobreprecio = precio de venta >= 1.5 x valor de mercado -> descartar
  - Equilibrio posicional antes que profundidad
"""
from datetime import datetime
from .client import POSITIONS

BID_MARKUP = 1.10
OVERPRICE = 1.50


def eur(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".") + " €"
    except (TypeError, ValueError):
        return "?"


def _pm(item: dict) -> dict:
    """Extrae el playerMaster de un jugador de plantilla o de mercado."""
    return item.get("playerMaster") or item.get("player") or item


def _pos(p: dict) -> str:
    return POSITIONS.get(p.get("positionId"), "?")


def _ratio(p: dict):
    """Puntos por millón de valor de mercado (mayor = mejor relación)."""
    mv, pts = p.get("marketValue"), p.get("points")
    if not mv or pts is None:
        return None
    return round(pts / (mv / 1_000_000), 2)


def squad_section(team: dict, teams_map: dict) -> str:
    players = team.get("players") or []
    rows, by_pos = [], {}
    for it in players:
        p = _pm(it)
        pos = _pos(p)
        by_pos[pos] = by_pos.get(pos, 0) + 1
        club = teams_map.get(str(p.get("teamId")), {}).get("shortName", "")
        clause = it.get("buyoutClause")
        rows.append((p.get("positionId", 9), (
            f"| {pos} | {p.get('nickname') or p.get('name')} | {club} | {eur(p.get('marketValue'))} "
            f"| {p.get('points', '?')} | {_ratio(p) or '-'} | {eur(clause) if clause else '-'} | {p.get('playerStatus', '')} |"
        )))
    rows.sort(key=lambda r: r[0])
    balance = ", ".join(f"{k}: {v}" for k, v in sorted(by_pos.items(), key=lambda kv: list(POSITIONS.values()).index(kv[0]) if kv[0] in POSITIONS.values() else 9))
    out = [f"**Equilibrio posicional:** {balance} ({len(players)} jugadores)", "",
           "| Pos | Jugador | Club | Valor | Pts | Pts/M€ | Cláusula | Estado |",
           "|---|---|---|---|---|---|---|---|"]
    out += [r[1] for r in rows]
    return "\n".join(out)


def market_section(market: list, my_team_id, teams_map: dict) -> str:
    rows = []
    for it in market:
        p = _pm(it)
        mv = p.get("marketValue") or 0
        sale = it.get("salePrice") or mv
        markup = (sale / mv) if mv else None
        seller = (it.get("sellerTeam") or {}).get("manager", {}).get("managerName") or ("LaLiga" if it.get("discr") == "marketPlayerLeague" else "?")
        mine = str((it.get("sellerTeam") or {}).get("id")) == str(my_team_id)
        if markup is None:
            flag = ""
        elif markup >= OVERPRICE:
            flag = "🚫 sobreprecio"
        elif markup > 1.15:
            flag = "⚠️ caro"
        else:
            flag = "✅"
        suggested = int(mv * BID_MARKUP) if mv else None
        suggested_str = eur(max(suggested, sale)) if suggested else "-"
        club = teams_map.get(str(p.get("teamId")), {}).get("shortName", "")
        exp = (it.get("expirationDate") or "")[:16].replace("T", " ")
        rows.append((mv, (
            f"| {_pos(p)} | {p.get('nickname') or p.get('name')} | {club} | {eur(mv)} | {eur(sale)} "
            f"| {f'{markup:.0%}' if markup else '-'} | {p.get('points', '?')} | {_ratio(p) or '-'} "
            f"| {'(mío) ' if mine else ''}{seller} | {it.get('numberOfBids', it.get('bids', '-'))} | {exp} | {flag} | {suggested_str} |"
        )))
    rows.sort(key=lambda r: -(r[0] or 0))
    out = ["| Pos | Jugador | Club | Valor | Precio venta | Precio/Valor | Pts | Pts/M€ | Vendedor | Pujas | Expira | Señal | Puja ref. (+10%) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    out += [r[1] for r in rows]
    return "\n".join(out)


def standing_section(standing: list, my_team_id) -> str:
    out = ["| # | Equipo | Mánager | Puntos | Valor |", "|---|---|---|---|---|"]
    for i, e in enumerate(standing, 1):
        t = e.get("team") or e
        mgr = (t.get("manager") or {}).get("managerName") or e.get("manager") or ""
        pts = e.get("points") or t.get("teamPoints") or t.get("points")
        me = " ⬅️" if str(t.get("id")) == str(my_team_id) else ""
        out.append(f"| {e.get('position', i)} | {t.get('name', '')}{me} | {mgr} | {pts} | {eur(t.get('teamValue') or e.get('teamValue'))} |")
    return "\n".join(out)


def top_value_section(players: list, teams_map: dict, n=25, min_points=10) -> str:
    """Mejores Pts/M€ de toda la liga (no solo del mercado): candidatos a fichar cuando salgan."""
    cands = [p for p in players if (p.get("points") or 0) >= min_points and p.get("marketValue") and p.get("positionId") in (1, 2, 3, 4)]
    cands.sort(key=lambda p: -(_ratio(p) or 0))
    out = ["| Pos | Jugador | Club | Valor | Pts | Pts/M€ |", "|---|---|---|---|---|---|"]
    for p in cands[:n]:
        club = teams_map.get(str(p.get("teamId")), {}).get("shortName", "")
        out.append(f"| {_pos(p)} | {p.get('nickname') or p.get('name')} | {club} | {eur(p.get('marketValue'))} | {p.get('points')} | {_ratio(p)} |")
    return "\n".join(out)


def build_report(*, league_name, week, my_team, money, standing, market, players, teams_map, my_team_id) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    balance = money if isinstance(money, (int, float)) else (money or {}).get("teamMoney", money)
    parts = [
        f"# Informe LaLiga Fantasy — {league_name}",
        f"_Generado {now} · Jornada actual: {week}_",
        "",
        f"## Presupuesto",
        f"Saldo disponible: **{eur(balance)}** · Valor de plantilla: **{eur(my_team.get('teamValue'))}**",
        "",
        "## Mi plantilla",
        squad_section(my_team, teams_map),
        "",
        "## Mercado ahora mismo",
        market_section(market, my_team_id, teams_map),
        "",
        "## Clasificación",
        standing_section(standing, my_team_id),
        "",
        "## Mejor relación puntos/valor de la liga (posibles objetivos)",
        top_value_section(players, teams_map),
        "",
        "---",
        "_Reglas: puja de referencia = valor ×1.10 · sobreprecio = venta ≥ 1.5× valor · equilibrar posiciones antes de añadir profundidad._",
    ]
    return "\n".join(parts)

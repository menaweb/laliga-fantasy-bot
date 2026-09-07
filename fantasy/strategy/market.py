"""Pujas (nuevas, modificar, cancelar), ventas, retiradas y ofertas recibidas."""
from datetime import datetime, timedelta

from ..config import ABSOLUTE_CAP, POS_NAMES
from ..models import Action, norm_player
from ..state import parse_dt
from .squad import LINES, best_xi, gaps, surplus, weakest_in_xi, xi_set


def _market_entry(it: dict) -> dict:
    p = norm_player(it.get("playerMaster") or {})
    return {"market_id": str(it.get("id")), "player": p, "salePrice": int(it.get("salePrice") or p["marketValue"]),
            "expiration": parse_dt(it.get("expirationDate")), "discr": it.get("discr"),
            "seller": str((it.get("sellerTeam") or {}).get("id") or ""), "numberOfBids": it.get("numberOfBids")}


def bid_price(fair: int, mv: int, sale_price: int, markup: float, cfg) -> int | None:
    """Precio de puja o None si el ítem está sobreprecio."""
    cap = int(mv * min(cfg.bids.hard_cap_ratio, ABSOLUTE_CAP - 0.01))
    if sale_price > cap:
        return None
    price = max(int(fair * markup), sale_price, mv)
    return min(price, cap)


def plan_offers(snap, valuer, cfg, ledger) -> list:
    """Ofertas recibidas por mis jugadores listados: aceptar/rechazar."""
    actions = []
    squad = snap.squad()
    xi = xi_set(snap.current_xi())
    for e in squad:
        if not e["onSale"]:
            continue
        market_id = str(e["onSale"].get("id"))
        for o in snap.offers.get(e["ptid"], []) or []:
            if o.get("status") not in (None, "pending") or str(o.get("id")) in ledger.handled_offers:
                continue
            money = int(o.get("money") or 0)
            fair = valuer.fair(e["player"])
            starter = e["ptid"] in xi
            ours = any(str(l.get("player_id")) == e["player"]["id"] for l in ledger.listings)
            ratio = cfg.sales.accept_offer_ratio_starter if starter else cfg.sales.accept_offer_ratio_bench
            who = "LaLiga" if o.get("isFromMarket") else "mánager"
            if starter and not ours:
                actions.append(Action("reject_offer", e["player"]["id"], e["player"]["nickname"], 0,
                                      f"oferta {who} {money:,} por un titular que no listamos nosotros".replace(",", "."),
                                      {"league_id": snap.league_id, "market_id": market_id, "offer_id": str(o.get("id"))},
                                      market_value=e["player"]["marketValue"]))
            elif money >= fair * ratio:
                actions.append(Action("accept_offer", e["player"]["id"], e["player"]["nickname"], 0,
                                      f"oferta {who} {money:,} >= {ratio:.2f}×valor justo {fair:,}".replace(",", "."),
                                      {"league_id": snap.league_id, "market_id": market_id, "offer_id": str(o.get("id")), "offer_money": money},
                                      market_value=e["player"]["marketValue"]))
            else:
                actions.append(Action("reject_offer", e["player"]["id"], e["player"]["nickname"], 0,
                                      f"oferta {who} {money:,} < {ratio:.2f}×valor justo {fair:,}".replace(",", "."),
                                      {"league_id": snap.league_id, "market_id": market_id, "offer_id": str(o.get("id"))},
                                      market_value=e["player"]["marketValue"]))
    return actions


def plan_sales(snap, valuer, cfg, ledger, now: datetime, fund: dict | None = None) -> list:
    """Listar sobrantes, vender para financiar un upgrade claro y retirar listados viejos sin oferta.
    fund = info['unaffordable_best'] de plan_bids: {player, price, gain, missing, exp}."""
    actions = []
    entries = [e for e in snap.squad() if e["player"]["positionId"] in (1, 2, 3, 4)]
    xi = best_xi(entries, valuer, snap.formations or ["4,4,2"]) or snap.current_xi()
    need_liquidity = int(fund["missing"]) if fund else 0
    # retirar listados caducos sin oferta útil
    for e in entries:
        if not e["onSale"]:
            continue
        mid = str(e["onSale"].get("id"))
        ours = next((l for l in ledger.listings if str(l.get("market_id")) == mid), None)
        listed_at = parse_dt(ours.get("listed_at")) if ours and ours.get("listed_at") else None
        if not listed_at:
            exp = parse_dt(e["onSale"].get("expirationDate"))
            listed_at = (exp - timedelta(hours=cfg.sales.listing_hours)) if exp else None
        offers = snap.offers.get(e["ptid"], []) or []
        if listed_at and now - listed_at > timedelta(hours=cfg.sales.withdraw_after_hours) and not offers:
            actions.append(Action("withdraw", e["player"]["id"], e["player"]["nickname"], 0,
                                  f"listado {cfg.sales.withdraw_after_hours}h sin ofertas",
                                  {"league_id": snap.league_id, "market_id": str(e["onSale"].get("id"))},
                                  market_value=e["player"]["marketValue"]))
    # nuevos listados
    n = 0
    cands = surplus(entries, xi, valuer)
    for e in sorted(cands, key=lambda e: valuer.exp(e["player"])):
        if e["onSale"] or n >= cfg.sales.max_new_listings_per_run:
            continue
        ev = valuer.evaluate(e["player"])
        trend = ev["trend"]
        squad_full = len(snap.squad()) >= cfg.squad.max_size
        reasons = []
        if trend is not None and trend <= cfg.sales.trend_sell_threshold:
            reasons.append(f"tend7 {trend:+.0%}")
        if squad_full:
            reasons.append("plantilla llena")
        if need_liquidity > 0:
            reasons.append("liquidez para fichar")
        if not reasons:
            continue
        price = max(int(ev["fair"] * cfg.sales.bench_list_ratio), e["player"]["marketValue"])
        actions.append(Action("sell", e["player"]["id"], e["player"]["nickname"], 0,
                              f"sobrante ({', '.join(reasons)}) · {ev['exp']:.1f} pts esp · precio {price:,}".replace(",", "."),
                              {"league_id": snap.league_id, "player_team_id": e["ptid"], "sale_price": price},
                              market_value=e["player"]["marketValue"]))
        n += 1
    # venta para financiar: hay un fichaje claro que no cabe en caja -> listar al peor valor que lo financie
    if fund and need_liquidity > 0 and not any(a.kind == "sell" for a in actions) and not ledger.listings:
        target_exp = float(fund.get("exp") or 0)
        cands = []
        for e in entries:
            p = e["player"]
            if e["onSale"] or p["marketValue"] < need_liquidity or valuer.exp(p) > target_exp - cfg.bids.min_gain_points:
                continue
            rest = [x for x in entries if x["ptid"] != e["ptid"]]
            cnt = {"POR": 0, "DEF": 0, "MED": 0, "DEL": 0}
            for x in rest:
                cnt[POS_NAMES[x["player"]["positionId"]]] += 1
            pos = POS_NAMES[p["positionId"]]
            if cnt[pos] < cfg.squad.min_per_pos.get(pos, 0) or len(rest) < cfg.squad.min_size:
                continue
            cands.append((valuer.exp(p) / max(p["marketValue"], 1), e))
        if cands:
            cands.sort(key=lambda t: t[0])
            e = cands[0][1]
            ev = valuer.evaluate(e["player"])
            price = max(int(ev["fair"] * cfg.sales.fund_list_ratio), e["player"]["marketValue"])
            actions.append(Action("sell", e["player"]["id"], e["player"]["nickname"], 0,
                                  f"financiar fichaje de {fund['player']} (faltan {need_liquidity:,}) · {ev['exp']:.1f} pts esp · precio {price:,}".replace(",", "."),
                                  {"league_id": snap.league_id, "player_team_id": e["ptid"], "sale_price": price, "fund": fund["player"]},
                                  market_value=e["player"]["marketValue"]))
    return actions


def plan_bids(snap, valuer, cfg, ledger, now: datetime) -> tuple[list, dict]:
    """Cancelar pujas que ya no aportan; pujar por huecos críticos y upgrades del once."""
    actions = []
    entries = [e for e in snap.squad() if e["player"]["positionId"] in (1, 2, 3, 4)]
    xi = best_xi(entries, valuer, snap.formations or ["4,4,2"]) or snap.current_xi()
    my_ids = {e["player"]["id"] for e in entries}
    market = [_market_entry(it) for it in snap.market]
    market = [m for m in market if m["seller"] != snap.team_id and m["player"]["positionId"] in (1, 2, 3, 4)]
    by_market_id = {m["market_id"]: m for m in market}

    def gain_of(p: dict) -> float:
        weakest = weakest_in_xi(entries, xi, valuer, p["positionId"])
        return valuer.exp(p) - (valuer.exp(weakest["player"]) if weakest else 0.0)

    # 1) revisar pujas activas
    for b in list(ledger.bids):
        m = by_market_id.get(str(b["market_id"]))
        if not m:
            continue
        g = gain_of(m["player"])
        if g < cfg.bids.cancel_if_gain_below and b.get("bid_id"):
            actions.append(Action("cancel_bid", m["player"]["id"], m["player"]["nickname"], 0,
                                  f"ya no aporta ({g:+.1f} pts)", {"league_id": snap.league_id, "market_id": m["market_id"], "bid_id": b["bid_id"]},
                                  market_value=m["player"]["marketValue"]))

    projected = snap.projected_money
    critical = gaps(entries, valuer, cfg, xi)
    count_gaps = gaps(entries, valuer, cfg)        # faltan cuerpos: cualquier disponible ayuda
    squad_size = len(snap.squad())
    room = cfg.squad.max_size - squad_size
    spent, n_new = 0, 0
    scored = []
    for m in market:
        p = m["player"]
        if p["id"] in my_ids or ledger.bid_for(m["market_id"]) or valuer.availability(p) <= 0:
            continue
        if m["expiration"] and m["expiration"] <= now:
            continue
        g = gain_of(p)
        pos = POS_NAMES[p["positionId"]]
        is_gap = pos in critical
        if g < cfg.bids.min_gain_points and pos not in count_gaps:
            continue   # un hueco por titular flojo solo se cubre con alguien que mejore el once de verdad
        if pos not in count_gaps and valuer.exp(p) < float(cfg.squad.get("weak_starter_exp", 0) or 0):
            continue
        markup = cfg.bids.markup_critical if is_gap else cfg.bids.markup_default
        price = bid_price(valuer.fair(p), p["marketValue"], m["salePrice"], markup, cfg)
        if price is None:
            continue
        scored.append((is_gap, g / max(price, 1) * 1e6, g, price, m))
    scored.sort(key=lambda t: (-int(t[0]), -t[1]))
    for is_gap, score, g, price, m in scored:
        if n_new >= cfg.bids.max_new_bids_per_run or len(ledger.bids) + n_new >= cfg.money.max_pending_bids:
            break
        if room - n_new <= 0:
            break
        if projected - spent - price < cfg.money.reserve:
            continue
        p = m["player"]
        actions.append(Action("bid", p["id"], p["nickname"], price,
                              f"{'HUECO ' + POS_NAMES[p['positionId']] + ' ' if is_gap else ''}+{g:.1f} pts al once · {valuer.evaluate(p)['reason']}",
                              {"league_id": snap.league_id, "market_id": m["market_id"], "money": price},
                              market_value=p["marketValue"]))
        spent += price
        n_new += 1
    info = {"projected": projected, "critical": critical, "candidates": len(scored), "unaffordable_best": None}
    # ¿hay un upgrade claro que no cabe en caja? -> pedir liquidez a plan_sales
    for is_gap, score, g, price, m in scored:
        if price > projected - spent and g >= cfg.bids.min_gain_points:
            info["unaffordable_best"] = {"player": m["player"]["nickname"], "price": price, "gain": g,
                                         "missing": price - (projected - spent), "exp": valuer.exp(m["player"])}
            break
    return actions, info

"""
Un run completo del gestor: auth -> snapshot -> valoraciones -> decisiones -> guard/executor -> log + Telegram.
Orden fijo, sin bucles, sin reintentos. Cualquier ApiError aborta el run.
"""
import os
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import notify, vault
from .auth import AuthError, refresh_for_ci, get_bearer, _load as load_local_tokens
from .client import ApiError, FantasyClient
from .executor import Executor
from .models import Action
from .guard import Guard
from .probable import fetch_probables
from .state import DecisionLog, Ledger, Snapshot, ValueHistory, load_cache, save_cache, save_snapshot
from .strategy.clauses import plan_clause_pays, plan_clause_raises
from .strategy.lineup import plan_lineup
from .strategy.market import plan_bids, plan_offers, plan_sales
from .strategy.value import Valuer


def _bearer(cfg, state_dir: str) -> str:
    """CI: refresh token cifrado en state/. Local: tokens.json (get_bearer)."""
    if os.getenv("CI") or os.getenv("STATE_KEY") and os.path.exists(os.path.join(state_dir, "auth.enc")):
        tokens = vault.load_refresh_tokens(state_dir)
        if not tokens:
            raise AuthError("state/auth.enc no existe: ejecuta `python main.py push-token` en local")
        t = refresh_for_ci(tokens)
        if t.get("refresh_token") and t["refresh_token"] != tokens[0]:
            vault.save_refresh_token(state_dir, t["refresh_token"])
        return t["bearer"]
    return get_bearer(os.getenv("LALIGA_EMAIL"), os.getenv("LALIGA_PASSWORD"))


def run_once(cfg, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(cfg.timezone)
    local = now.astimezone(tz)
    today = local.strftime("%Y-%m-%d")
    state_dir = cfg.state_dir
    os.makedirs(state_dir, exist_ok=True)
    ledger, log = Ledger(state_dir), DecisionLog(state_dir)
    mode = "DRY" if cfg.dry_run else "LIVE"
    run = {"mode": mode, "results": [], "notes": [], "errors": [], "started": now.isoformat()}
    broken_flag = os.path.join(state_dir, "auth_broken.flag")

    try:
        if os.path.exists(broken_flag):
            raise AuthError("auth marcada como rota: ejecuta `python main.py login` y `python main.py push-token`")
        bearer = _bearer(cfg, state_dir)
        write_ok = (not cfg.dry_run) and (not cfg.kill_switch) and bool(cfg.enabled_writes)
        c = FantasyClient(bearer, allow_writes=write_ok, max_requests=cfg.run.max_requests_per_run)

        cache = load_cache(state_dir)
        snap = Snapshot.fetch(c, cfg, cache)
        save_cache(state_dir, cache)
        save_snapshot(state_dir, snap)
        history = ValueHistory(state_dir)
        history.record_today(snap.players, today)
        ledger.reconcile(snap)

        next_week = snap.week_number + 1 if snap.is_live else snap.week_number
        clubs = {str(m["localId"]) for m in snap.matches(next_week)} | {str(m["visitorId"]) for m in snap.matches(next_week)}
        probable, psum = fetch_probables(snap, cfg, os.path.join(state_dir, "probable_cache.json"), clubs, now)
        run["notes"].append(psum)
        v = Valuer(snap, history, probable, cfg, today)

        actions = []
        rw = cfg.get("reward") or {}
        if rw.get("enabled") and rw.get("rewarded_ad_type") and rw.get("rewarded_ad") is not None:
            try:
                chk = c.check_daily_reward(snap.league_id, snap.team_id) or {}
                if isinstance(chk, dict) and int(chk.get("dailyRewardsRedeemed") or 0) == 0:
                    body = {"teamId": int(snap.team_id), "rewardedAdType": rw["rewarded_ad_type"], "rewardedAd": rw["rewarded_ad"]}
                    actions.append(Action("daily_reward", None, "Recompensa diaria", 0, "100.000 € sin reclamar hoy",
                                          {"league_id": snap.league_id, "team_id": snap.team_id, "body": body}))
            except ApiError as e:
                if "429" in str(e):
                    raise
                run["notes"].append(f"recompensa diaria: no se pudo comprobar ({str(e)[-60:]})")
        a, why = plan_lineup(snap, v, cfg, now)
        if a:
            actions.append(a)
        else:
            run["notes"].append(f"alineación: {why}")
        actions += plan_offers(snap, v, cfg, ledger)
        bids, info = plan_bids(snap, v, cfg, ledger, now)
        actions += bids
        actions += plan_sales(snap, v, cfg, ledger, now, fund=info.get("unaffordable_best"))
        planned_spend = sum(x.amount for x in bids)
        budget_left = info["projected"] - planned_spend
        actions += plan_clause_pays(snap, v, cfg, now, budget_left)
        if not info.get("unaffordable_best"):
            actions += plan_clause_raises(snap, v, cfg, now, budget_left - sum(x.amount for x in actions if x.kind == "clause_pay"))
        else:
            run["notes"].append(f"caja reservada para {info['unaffordable_best']['player']} (faltan {info['unaffordable_best']['missing']:,} €)".replace(",", "."))
        if info.get("critical"):
            run["notes"].append(f"huecos críticos: {', '.join(info['critical'])}")

        guard = Guard(cfg, snap, ledger, now)
        ex = Executor(c, guard, ledger, dry_run=cfg.dry_run)
        run["results"] = ex.run(actions)
        # El dinero de una venta aceptada entra al instante: releer saldo/plantilla y pujar en este mismo run.
        money_moved = any(r.status == "OK" and r.action.kind in ("accept_offer", "clause_pay", "cancel_bid") for r in run["results"])
        if money_moved and not cfg.dry_run:
            m = c.money(snap.team_id)
            snap.money = int(m.get("teamMoney", 0)) if isinstance(m, dict) else int(m or 0)
            snap.investment = int(m.get("teamInvestment", 0) or 0) if isinstance(m, dict) else 0
            snap.team = c.team(snap.league_id, snap.team_id) or snap.team
            snap.market = c.market(snap.league_id) or snap.market
            ledger.reconcile(snap)
            guard.refresh(snap)
            bids2, info2 = plan_bids(snap, v, cfg, ledger, now)
            if bids2:
                run["notes"].append(f"replanificación con saldo actualizado ({snap.projected_money:,} €)".replace(",", "."))
                run["results"] += ex.run(bids2)
            info["projected"] = snap.projected_money
            if info2.get("unaffordable_best"):
                run["notes"].append(f"sigue sin caber {info2['unaffordable_best']['player']} (faltan {info2['unaffordable_best']['missing']:,} €)".replace(",", "."))
        run.update({"week": snap.week_number, "live": snap.is_live, "money": snap.money, "projected": info["projected"],
                    "position": snap.team.get("position"), "points": snap.team.get("teamPoints"), "requests": c.request_count})
        first_live = [r.action.group for r in run["results"] if r.status == "OK" and r.action.group not in ledger.live_writes_seen]
        for g in first_live:
            ledger.live_writes_seen.append(g)
            run["notes"].append(f"primera escritura LIVE del grupo '{g}'")
        ledger.runs.append({"ts": now.isoformat(), "mode": mode, "actions": len([r for r in run["results"] if r.status in ("OK", "DRY")]),
                            "spend": guard.spent, "requests": c.request_count})
    except AuthError as e:
        run["errors"].append(f"AUTH ROTA: {e}. Ejecuta en el Mac: python main.py login && python main.py push-token")
        open(broken_flag, "w").close()
        ledger.runs.append({"ts": now.isoformat(), "mode": mode, "error": f"auth: {e}"})
    except ApiError as e:
        run["errors"].append(f"API: {e}")
        ledger.runs.append({"ts": now.isoformat(), "mode": mode, "error": f"api: {e}"[:200]})
    except Exception as e:  # noqa: BLE001 - un run nunca debe morir sin log ni aviso
        run["errors"].append(f"BUG: {type(e).__name__}: {e}")
        ledger.runs.append({"ts": now.isoformat(), "mode": mode, "error": f"bug: {e}"[:200]})
        traceback.print_exc()

    ledger.save()
    header = f"{local.strftime('%H:%M')} {mode} J{run.get('week', '?')}"
    log.append(today, header, [r.line() for r in run["results"]] + run["notes"] + run["errors"])
    text = notify.format_run(run)
    idle = not run["results"] and not run["errors"]
    if not (idle and cfg.run.quiet_when_idle and local.hour != cfg.run.daily_summary_hour_local):
        print("telegram enviado:", notify.send(text))
    else:
        print(text)
    if run["errors"] and ledger.consecutive_failures() == 3:
        notify.send("🚨 3 runs seguidos con error. Revisa el workflow en GitHub.")
    return run

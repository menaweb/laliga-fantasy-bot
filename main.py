#!/usr/bin/env python3
"""
Uso:
  python main.py login      -> comprueba que el login funciona (abre el navegador si hace falta)
  python main.py token      -> pega a mano un token sacado de DevTools (plan B)
  python main.py ligas      -> lista tus ligas (para elegir LALIGA_LEAGUE_ID)
  python main.py informe    -> genera data/informe_YYYY-MM-DD.md para pegar en Claude
  python main.py raw        -> guarda en data/ los JSON crudos (para depurar si algo no cuadra)
  python main.py run [--live]   -> un run del gestor autónomo (por defecto dry-run; --live respeta ENABLED_WRITES)
  python main.py push-token [--set-key] -> cifra el refresh token en state/auth.enc y lo sube al repo
  python main.py verify-writes  -> Fase 0: escrituras de verificación una a una, con confirmación
  python main.py scrub      -> copia data/raw_* a tests/fixtures anonimizando mánagers
"""
import json
import os
import sys
from datetime import date
from dotenv import load_dotenv

from fantasy.auth import get_bearer, save_manual_token, AuthError, _load as load_tokens
from fantasy.client import FantasyClient, ApiError
from fantasy.report import build_report

load_dotenv()
EMAIL = os.getenv("LALIGA_EMAIL")
PASSWORD = os.getenv("LALIGA_PASSWORD")
LEAGUE_ID = os.getenv("LALIGA_LEAGUE_ID") or None
os.makedirs("data", exist_ok=True)


def dump(name, obj):
    with open(f"data/{name}.json", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def client() -> FantasyClient:
    # Con LALIGA_EMAIL+LALIGA_PASSWORD usa el grant de contraseña (solo cuentas locales).
    # Si faltan (cuenta Google/Apple), abre el login interactivo en el navegador.
    return FantasyClient(get_bearer(EMAIL, PASSWORD), allow_writes=False)


def pick_league(c: FantasyClient) -> dict:
    leagues = c.leagues() or []
    if not leagues:
        sys.exit("No se han encontrado ligas en tu cuenta.")
    if LEAGUE_ID:
        for lg in leagues:
            if str(lg.get("id")) == str(LEAGUE_ID):
                return lg
        sys.exit(f"LALIGA_LEAGUE_ID={LEAGUE_ID} no está entre tus ligas. Ejecuta: python main.py ligas")
    if len(leagues) > 1:
        print("Tienes varias ligas; usando la primera. Fija LALIGA_LEAGUE_ID en .env para elegir.")
    return leagues[0]


def find_my_team(c: FantasyClient, league: dict):
    """Devuelve (team_id) del usuario en la liga: primero por el objeto liga, si no, por la clasificación."""
    tid = (league.get("team") or {}).get("id") or league.get("teamId")
    if tid:
        return tid
    me = c.me() or {}
    my_ids = {str(me.get(k)) for k in ("id", "userId", "managerId") if me.get(k)}
    for e in c.standing(league["id"]) or []:
        t = e.get("team") or e
        mgr = t.get("manager") or {}
        if str(mgr.get("id")) in my_ids or str(e.get("userId")) in my_ids:
            return t.get("id")
    sys.exit("No he podido identificar tu equipo en la liga. Ejecuta `python main.py raw` y mándame data/standing.json y data/me.json.")


def cmd_login():
    try:
        c = client()
        me = c.me()
        print("Login OK. Usuario:", me.get("managerName") or me.get("username") or me.get("id"))
    except AuthError as e:
        sys.exit(f"Error de login: {e}")


def cmd_token():
    print("Pega el valor de la cabecera Authorization (sin 'Bearer ') sacado de DevTools en fantasy.laliga.com.")
    try:
        save_manual_token(input("Token: "))
    except AuthError as e:
        sys.exit(f"Error: {e}")
    print("Token guardado en tokens.json. Ejecuta: python main.py login")


def cmd_ligas():
    c = client()
    for lg in c.leagues() or []:
        print(f"{lg.get('id')}\t{lg.get('name')}")


def cmd_raw():
    """Captura JSON crudos de todo lo que usa el motor. Solo lectura (~25 peticiones)."""
    from datetime import datetime
    c = client()
    league = pick_league(c)
    lid = league["id"]
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = f"data/raw_{stamp}"
    os.makedirs(out, exist_ok=True)

    def save(name, fn):
        try:
            obj = fn()
        except ApiError as e:
            obj = {"_error": str(e)}
            print(f"  {name}: ERROR {str(e)[:120]}")
        with open(f"{out}/{name}.json", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return obj if not (isinstance(obj, dict) and "_error" in obj) else None

    me = save("me", c.me)
    save("league", lambda: league)
    standing = save("standing", lambda: c.standing(lid)) or []
    market = save("market", lambda: c.market(lid)) or []
    tid = find_my_team(c, league)
    team = save("team", lambda: c.team(lid, tid)) or {}
    save("money", lambda: c.money(tid))
    week = save("week", c.current_week) or {}
    wn = week.get("weekNumber") or week.get("number") or week.get("id")
    save("lineup", lambda: c.lineup(tid))
    if wn:
        save(f"lineup_week_{wn}", lambda: c.lineup_week(tid, wn))
        save(f"calendar_{wn}", lambda: c.calendar(wn))
        save(f"calendar_{int(wn)+1}", lambda: c.calendar(int(wn) + 1))
        save(f"standing_week_{wn}", lambda: c.standing_week(lid, wn))
    save("formations_free", lambda: c.formations("free"))
    save("formations_premium", lambda: c.formations("premium"))
    save("activity_0", lambda: c.activity(lid, 0))
    save("activity_1", lambda: c.activity(lid, 1))
    save("players", c.players)
    save("teams_master", c.teams_master)
    # detalle de 3 jugadores: uno mío, uno del mercado, uno de un rival
    mine = (team.get("players") or [])
    if mine:
        pm = mine[0].get("playerMaster") or {}
        save("player_detail_mine", lambda: c.player_detail(pm.get("id"), lid))
        save("received_offers_mine0", lambda: c.received_offers(lid, mine[0].get("playerTeamId")))
        save("check_shield_mine0", lambda: c.check_shield(lid, mine[0].get("playerTeamId")))
    if market:
        pm = market[0].get("playerMaster") or {}
        save("player_detail_market", lambda: c.player_detail(pm.get("id"), lid))
    rivals = [(e.get("team") or e) for e in standing if str((e.get("team") or e).get("id")) != str(tid)]
    if rivals:
        rt = save("team_rival0", lambda: c.team(lid, rivals[0].get("id"))) or {}
        rp = (rt.get("players") or [])
        if rp:
            pm = rp[0].get("playerMaster") or {}
            save("player_detail_rival", lambda: c.player_detail(pm.get("id"), lid))
    print(f"JSON guardados en {out}/ ({c.request_count} peticiones)")


def cmd_informe():
    c = client()
    league = pick_league(c)
    lid = league["id"]
    tid = find_my_team(c, league)
    teams_map = {str(t.get("id")): t for t in (c.teams_master() or []) if isinstance(t, dict)}
    week = c.current_week() or {}
    week_no = week.get("weekNumber") or week.get("number") or week.get("id") or "?"
    my_team = c.team(lid, tid) or {}
    money = c.money(tid)
    standing = c.standing(lid) or []
    market = c.market(lid) or []
    players = c.players() or []

    md = build_report(league_name=league.get("name", lid), week=week_no, my_team=my_team, money=money,
                      standing=standing, market=market, players=players, teams_map=teams_map, my_team_id=tid)
    path = f"data/informe_{date.today().isoformat()}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\n>>> Informe guardado en {path}. Pégalo en el chat con Claude.")


def cmd_run():
    from fantasy.config import load_config
    from fantasy.engine import run_once
    if "--live" not in sys.argv:
        os.environ["DRY_RUN"] = "true"
    cfg = load_config()
    print(f"Run {'LIVE' if not cfg.dry_run else 'DRY'} · escrituras habilitadas: {cfg.enabled_writes or '(ninguna)'} · kill_switch={cfg.kill_switch}")
    r = run_once(cfg)
    if r.get("errors"):
        sys.exit(1)


def cmd_push_token():
    """Cifra el refresh_token de tokens.json en state/auth.enc y hace commit+push."""
    import subprocess
    from fantasy import vault
    t = load_tokens() or {}
    if not t.get("refresh_token"):
        sys.exit("tokens.json no tiene refresh_token: ejecuta `python main.py login` primero")
    if "--set-key" in sys.argv:
        key = vault.new_key()
        os.environ["STATE_KEY"] = key
        subprocess.run(["gh", "secret", "set", "STATE_KEY", "--body", key], check=True)
        with open(".env", "a", encoding="utf-8") as f:
            f.write(f"\nSTATE_KEY={key}\n")
        print("STATE_KEY generada, subida a GitHub y añadida a .env")
    if not os.getenv("STATE_KEY"):
        sys.exit("Falta STATE_KEY en .env (usa --set-key la primera vez)")
    state_dir = os.getenv("STATE_DIR", "state")
    vault.save_refresh_token(state_dir, t["refresh_token"])
    flag = os.path.join(state_dir, "auth_broken.flag")
    if os.path.exists(flag):
        os.remove(flag)
    subprocess.run(["git", "add", state_dir], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        subprocess.run(["git", "commit", "-m", "state: refresh token renovado"], check=True)
        subprocess.run(["git", "pull", "--rebase", "--autostash"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("state/auth.enc actualizado y subido")
    else:
        print("state/auth.enc sin cambios")


def cmd_verify_writes():
    """Fase 0: una escritura de cada tipo, reversible, con confirmación por acción. Rafa mirando la app."""
    from fantasy.config import load_config
    from fantasy.state import Snapshot
    cfg = load_config()
    c = FantasyClient(get_bearer(EMAIL, PASSWORD), allow_writes=True, max_requests=60)
    snap = Snapshot.fetch(c, cfg, {})
    tid, lid = snap.team_id, snap.league_id

    def ask(msg):
        return input(f"\n{msg} [s/N] ").strip().lower() == "s"

    xi = snap.current_xi()
    payload = {"goalkeeper": xi["goalkeeper"][0], "defender": xi["defender"], "midfield": xi["midfield"],
               "striker": xi["striker"], "tactical_formation": xi["formation"]}
    if ask(f"1) PUT lineup con el once ACTUAL sin cambios {payload['tactical_formation']} (no cambia nada)?"):
        print("   ->", c.set_lineup(tid, payload))
    cheapest = min((it for it in snap.market if str((it.get('sellerTeam') or {}).get('id')) != tid),
                   key=lambda it: it.get("salePrice") or 0, default=None)
    if cheapest:
        pm = cheapest["playerMaster"]; price = int(cheapest["salePrice"])
        if ask(f"2) Puja mínima {price:,} por {pm.get('nickname')} (id mercado {cheapest['id']}) y cancelarla después?".replace(",", ".")):
            r = c.bid(lid, cheapest["id"], price); print("   bid ->", r)
            print("   money tras pujar ->", c.money(tid))
            bid_id = (r or {}).get("id") if isinstance(r, dict) else None
            mk = next((it for it in (c.market(lid) or []) if str(it.get("id")) == str(cheapest["id"])), {})
            print("   ítem de mercado tras pujar ->", {k: v for k, v in mk.items() if k != "playerMaster"})
            if bid_id and ask(f"   cancelar puja {bid_id}?"):
                print("   cancel ->", c.cancel_bid(lid, cheapest["id"], bid_id))
                print("   money tras cancelar ->", c.money(tid))
    sq = sorted(snap.squad(), key=lambda e: e["player"]["marketValue"])
    cand = next((e for e in sq if not e["onSale"]), None)
    if cand:
        price = int(cand["player"]["marketValue"] * 1.45)
        if ask(f"3) Poner en venta a {cand['player']['nickname']} a {price:,} (1.45x, nadie lo compra) y retirarlo?".replace(",", ".")):
            r = c.sell(lid, cand["player"]["id"], price); print("   sell ->", r)
            mid = (r or {}).get("id") if isinstance(r, dict) else None
            if not mid:
                t2 = c.team(lid, tid)
                it = next((x for x in t2.get("players", []) if str(x["playerMaster"]["id"]) == cand["player"]["id"]), {})
                mid = (it.get("playerMarket") or {}).get("id")
            if mid and ask(f"   retirar listado {mid}?"):
                print("   withdraw ->", c.withdraw(lid, mid))
    t = load_tokens() or {}
    if t.get("refresh_token") and ask("4) Refrescar dos veces con el mismo refresh token (¿invalida el anterior?)"):
        from fantasy.auth import refresh
        old = t["refresh_token"]
        a = refresh(old); print("   refresh#1 ok, nuevo rt distinto:", a["refresh_token"] != old)
        try:
            refresh(old); print("   refresh#2 con el rt ANTIGUO: OK (no se invalida)")
        except AuthError as e:
            print("   refresh#2 con el rt ANTIGUO: FALLA ->", e)
    print(f"\nHecho ({c.request_count} peticiones).")


def cmd_scrub():
    import glob, re, shutil
    dirs = sorted(glob.glob("data/raw_*"))
    if not dirs:
        sys.exit("No hay data/raw_*: ejecuta `python main.py raw`")
    src, dst = dirs[-1], "tests/fixtures"
    os.makedirs(dst, exist_ok=True)
    names = {}
    def anon(obj):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if k in ("managerName",) and isinstance(v, str):
                    obj[k] = names.setdefault(v, f"manager{len(names) + 1}")
                elif k in ("avatar", "email", "images", "image", "lastStats", "playerStats", "assets", "badgeColor", "badgeWhite"):
                    obj[k] = None
                else:
                    anon(v)
        elif isinstance(obj, list):
            for x in obj:
                anon(x)
        return obj
    for f in glob.glob(f"{src}/*.json"):
        with open(f, encoding="utf-8") as fh:
            obj = json.load(fh)
        with open(os.path.join(dst, os.path.basename(f)), "w", encoding="utf-8") as fh:
            json.dump(anon(obj), fh, ensure_ascii=False)
    print(f"{src} -> {dst} ({len(names)} mánagers anonimizados)")


if __name__ == "__main__":
    cmds = {"login": cmd_login, "token": cmd_token, "ligas": cmd_ligas, "informe": cmd_informe, "raw": cmd_raw,
            "run": cmd_run, "push-token": cmd_push_token, "verify-writes": cmd_verify_writes, "scrub": cmd_scrub}
    arg = sys.argv[1] if len(sys.argv) > 1 else "informe"
    if arg not in cmds:
        sys.exit(__doc__)
    try:
        cmds[arg]()
    except ApiError as e:
        sys.exit(f"Error de API: {e}\nSi es un 404/400, la ruta puede haber cambiado: ejecuta `python main.py raw` y mándame el error.")

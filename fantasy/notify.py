"""Avisos por Telegram. Sin token: imprime por stdout. Nunca incluye secretos."""
import os
import requests

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX = 4000


def send(text: str) -> bool:
    if "Bearer " in text or "refresh_token" in text:
        text = "[mensaje bloqueado: contenía credenciales]"
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("\n--- TELEGRAM (sin token, stdout) ---\n" + text + "\n---")
        return False
    ok = True
    for i in range(0, len(text), MAX):
        chunk = text[i:i + MAX]
        try:
            r = requests.post(API.format(token=token), json={"chat_id": chat, "text": chunk, "disable_web_page_preview": True}, timeout=15)
            ok = ok and r.ok
        except requests.RequestException:
            ok = False
    return ok


def format_run(run: dict) -> str:
    """run: {week, live, mode, money, projected, results:[Result], notes:[str], errors:[str], position, points}"""
    eur = lambda n: f"{int(n):,} €".replace(",", ".")
    head = (f"🏟 J{run.get('week')}{' (en juego)' if run.get('live') else ''} · {run.get('mode')} · "
            f"{run.get('position')}º con {run.get('points')} pts\n"
            f"💰 saldo {eur(run.get('money', 0))} · proyectado {eur(run.get('projected', 0))}")
    lines = [head]
    done = [r for r in run.get("results", []) if r.status in ("OK", "DRY")]
    blocked = [r for r in run.get("results", []) if r.status == "BLOCKED"]
    errors = [r for r in run.get("results", []) if r.status == "ERROR"]
    if done:
        lines.append("\n✅ Acciones:" if run.get("mode") == "LIVE" else "\n🧪 Haría (dry-run):")
        lines += [f"• {r.action.describe()}" for r in done]
    if blocked:
        lines.append("\n⛔ Bloqueadas por el guard:")
        lines += [f"• {r.action.describe()} → {r.detail}" for r in blocked]
    if errors:
        lines.append("\n❌ Errores:")
        lines += [f"• {r.action.describe()} → {r.detail}" for r in errors]
    if run.get("notes"):
        lines.append("\nℹ️ " + "\n".join(run["notes"]))
    if run.get("errors"):
        lines.append("\n🚨 " + "\n".join(run["errors"]))
    return "\n".join(lines)

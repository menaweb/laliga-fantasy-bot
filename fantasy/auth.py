"""
Login contra el tenant Azure B2C de LaLiga (mismo flujo que la app oficial).
Devuelve un id_token que la API acepta como Bearer. Se cachea en tokens.json
y se refresca con el refresh_token cuando caduca (~24h).

Dos modos:
- Interactivo (cuentas Google/Apple/Facebook o cualquiera): Authorization Code + PKCE.
  Abre el navegador, te logueas, y pegas en la terminal la URL a la que te redirige.
- Contraseña (solo cuentas locales email/contraseña): grant "password".
"""
import base64
import hashlib
import json
import os
import re
import secrets
import time
import webbrowser
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

B2C_BASE = "https://login.laliga.es/laligadspprob2c.onmicrosoft.com/oauth2/v2.0"
TOKEN_URL = f"{B2C_BASE}/token"
AUTHORIZE_URL = f"{B2C_BASE}/authorize"
PASSWORD_POLICY = "B2C_1A_ResourceOwnerv2"
SIGNIN_POLICY = "B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN"  # flujo interactivo y refresh
REFRESH_POLICY = SIGNIN_POLICY
EMAIL_CLIENT_ID = "af88bcff-1157-40a0-b579-030728aacf0b"  # cliente nativo: admite el redirect authredirect://
REDIRECT_URI = "authredirect://com.lfp.laligafantasy"
TOKEN_FILE = os.getenv("LALIGA_TOKEN_FILE", "tokens.json")


class AuthError(Exception):
    pass


def _save(tokens: dict) -> None:
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def _load() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def _normalize(raw: dict) -> dict:
    expires_in = int(raw.get("expires_in") or raw.get("id_token_expires_in") or 86400)
    return {
        "bearer": raw.get("access_token") or raw.get("id_token"),
        "refresh_token": raw.get("refresh_token"),
        "expires_at": time.time() + expires_in - 120,  # margen de 2 min
    }


def _post_token(policy: str, data: dict) -> dict:
    r = requests.post(f"{TOKEN_URL}?p={policy}", data=data, timeout=20)
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {}
    if not r.ok or not (body.get("access_token") or body.get("id_token")):
        raise AuthError(body.get("error_description") or body.get("error") or f"HTTP {r.status_code}")
    return body


# ---------- modo contraseña (solo cuentas locales) ----------

def login(email: str, password: str) -> dict:
    data = {
        "grant_type": "password",
        "client_id": EMAIL_CLIENT_ID,
        "scope": f"openid {EMAIL_CLIENT_ID} offline_access",
        "redirect_uri": REDIRECT_URI,
        "username": email,
        "password": password,
        "response_type": "id_token",
    }
    tokens = _normalize(_post_token(PASSWORD_POLICY, data))
    _save(tokens)
    return tokens


# ---------- modo interactivo (Google, Apple, ...) ----------

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def build_authorize_url() -> tuple[str, str, str]:
    """Devuelve (url, code_verifier, state) para el flujo Authorization Code + PKCE."""
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(16)
    params = {
        "p": SIGNIN_POLICY,
        "client_id": EMAIL_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", verifier, state


def parse_redirect(pasted: str, expected_state: str) -> str:
    """Extrae el `code` de la URL de redirección (authredirect://...?code=...&state=...)."""
    pasted = pasted.strip().strip("'\"")
    if not pasted:
        raise AuthError("No has pegado nada.")
    # Admite pegar el mensaje entero del navegador ("Failed to launch 'authredirect://...' because ...")
    m = re.search(r"authredirect://[^\s'\"]+", pasted)
    if m:
        pasted = m.group(0)
    if "://" not in pasted and "=" not in pasted:
        return pasted  # el usuario ha pegado solo el code
    parts = urlsplit(pasted)
    q = parse_qs(parts.query)
    q.update(parse_qs(parts.fragment))
    if q.get("error"):
        raise AuthError(q.get("error_description", q["error"])[0])
    code = (q.get("code") or [None])[0]
    if not code:
        raise AuthError("La URL pegada no contiene `code=`. Copia la URL completa de la barra de direcciones.")
    state = (q.get("state") or [None])[0]
    if state and state != expected_state:
        raise AuthError("El `state` no coincide: vuelve a ejecutar el login y usa la URL de esta sesión.")
    if code.count(".") != 4:
        raise AuthError("El `code` ha llegado incompleto (la terminal recorta pegados largos). "
                        "Guarda la URL en un archivo, p.ej. redirect.txt, y pega la RUTA del archivo en vez de la URL.")
    return code


def exchange_code(code: str, verifier: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": EMAIL_CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "scope": "openid offline_access",
    }
    tokens = _normalize(_post_token(SIGNIN_POLICY, data))
    _save(tokens)
    return tokens


def login_interactive() -> dict:
    url, verifier, state = build_authorize_url()
    print("\n=== Login interactivo (Google / Apple / email) ===")
    print("1. Se va a abrir el navegador con la pantalla de login de LaLiga. Entra con tu cuenta.")
    print("2. Al terminar, el navegador intentará abrir una dirección que empieza por")
    print(f"   {REDIRECT_URI}?code=...  (dará error o quedará en blanco: es normal).")
    print("3. Copia esa URL COMPLETA (o el mensaje de error entero) y pégala aquí.")
    print("   Si el code llega recortado, guarda la URL en un archivo y pega aquí la ruta del archivo.")
    print("   Si el navegador no la muestra: DevTools > Network > 'Preserve log' > última petición")
    print("   a login.laliga.es > cabecera Location.\n")
    print("URL de login (por si no se abre sola):\n" + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        import readline  # noqa: F401  evita el límite de 1024 caracteres por línea de la terminal en macOS
    except ImportError:
        pass
    try:
        pasted = input("Pega aquí la URL de redirección (o la ruta de un archivo .txt que la contenga): ")
    except EOFError:
        raise AuthError("El login interactivo necesita una terminal. Ejecuta `python main.py login` a mano.")
    pasted = pasted.strip().strip("'\"")
    if pasted and os.path.isfile(os.path.expanduser(pasted)):
        with open(os.path.expanduser(pasted), encoding="utf-8") as f:
            pasted = f.read()
    code = parse_redirect(pasted, state)
    return exchange_code(code, verifier)


def save_manual_token(bearer: str, refresh_token: str | None = None) -> dict:
    """Guarda un token copiado a mano (p.ej. de DevTools en fantasy.laliga.com)."""
    tokens = _normalize({"id_token": bearer.strip(), "refresh_token": refresh_token})
    if not tokens["bearer"]:
        raise AuthError("Token vacío.")
    _save(tokens)
    return tokens


# ---------- refresh y punto de entrada ----------

def refresh(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": EMAIL_CLIENT_ID,
        "scope": "openid offline_access",
    }
    tokens = _normalize(_post_token(REFRESH_POLICY, data))
    if not tokens["refresh_token"]:
        tokens["refresh_token"] = refresh_token
    _save(tokens)
    return tokens


def refresh_for_ci(refresh_tokens: list) -> dict:
    """CI: prueba cada refresh token (actual, anterior). Devuelve {bearer, refresh_token, expires_at}."""
    last = None
    for rt in refresh_tokens:
        try:
            return refresh(rt)
        except AuthError as e:
            last = e
    raise AuthError(f"ningún refresh token válido ({last})")


def get_bearer(email: str | None = None, password: str | None = None) -> str:
    """Devuelve un token válido: caché -> refresh -> login (contraseña si hay; si no, interactivo)."""
    cached = _load()
    if cached and cached.get("bearer") and cached.get("expires_at", 0) > time.time():
        return cached["bearer"]
    if cached and cached.get("refresh_token"):
        try:
            return refresh(cached["refresh_token"])["bearer"]
        except AuthError as e:
            print(f"(refresh fallido: {e}; haciendo login de nuevo)")
    if email and password:
        return login(email, password)["bearer"]
    return login_interactive()["bearer"]

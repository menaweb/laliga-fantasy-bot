"""Refresh token cifrado (Fernet) en state/auth.enc con la clave STATE_KEY (secret de GitHub / .env)."""
import os
from cryptography.fernet import Fernet, InvalidToken


class VaultError(Exception):
    pass


def _key() -> bytes:
    k = os.getenv("STATE_KEY")
    if not k:
        raise VaultError("Falta STATE_KEY (secret de GitHub o variable en .env)")
    return k.encode()


def new_key() -> str:
    return Fernet.generate_key().decode()


def encrypt(text: str) -> bytes:
    return Fernet(_key()).encrypt(text.encode())


def decrypt(blob: bytes) -> str:
    try:
        return Fernet(_key()).decrypt(blob).decode()
    except InvalidToken:
        raise VaultError("STATE_KEY no descifra state/auth.enc (clave distinta o archivo corrupto)")


def save_refresh_token(state_dir: str, refresh_token: str) -> None:
    path = os.path.join(state_dir, "auth.enc")
    prev = os.path.join(state_dir, "auth.prev.enc")
    os.makedirs(state_dir, exist_ok=True)
    if os.path.exists(path):
        os.replace(path, prev)
    with open(path, "wb") as f:
        f.write(encrypt(refresh_token))


def load_refresh_tokens(state_dir: str) -> list:
    """[actual, anterior] descifrados (los que existan)."""
    out = []
    for name in ("auth.enc", "auth.prev.enc"):
        p = os.path.join(state_dir, name)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            blob = f.read()
        try:
            out.append(decrypt(blob))
        except VaultError:
            if name == "auth.enc":
                raise
            # el backup puede estar cifrado con una clave anterior: se ignora
    return out

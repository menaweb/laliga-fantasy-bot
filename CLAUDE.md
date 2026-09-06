# LaLiga Fantasy — gestor autónomo de Rafa

## Qué es esto
Gestor autónomo del equipo de Rafa en LaLiga Fantasy (app oficial, temporada 26/27, liga privada "Liga Tablerillo",
id 017900934, sin premios) usando la API no pública del juego. Corre en GitHub Actions cada hora sin el Mac de Rafa:
sincroniza la liga, decide alineación / pujas / ventas / cláusulas con reglas explicables, ejecuta dentro de límites
duros y avisa por Telegram. Objetivo: ganar la liga. Claude Code se usa para desarrollar, revisar decisiones
(`/jornada`) y ajustar `config.yaml`; NO para ejecutar escrituras a mano.

## Estructura
- `main.py` — CLI: `login`, `token`, `ligas`, `informe`, `raw`, `run [--live]`, `push-token [--set-key]`, `verify-writes`, `scrub`
- `config.yaml` — límites y perfil (agresivo). Editar + commit = el siguiente run lo aplica.
- `fantasy/auth.py` — OAuth B2C (Google: PKCE interactivo; CI: refresh token). `fantasy/vault.py` — token cifrado en `state/auth.enc`.
- `fantasy/client.py` — HTTP. Escritura bloqueada salvo `allow_writes=True` (solo lo activa `engine.py`).
- `fantasy/state.py` — Snapshot, histórico de valores, ledger de pujas, log de decisiones (`state/`, commiteado por CI).
- `fantasy/strategy/` — `value.py` (pts esperados), `squad.py`, `lineup.py`, `market.py`, `clauses.py`. Solo PROPONEN `Action`s.
- `fantasy/guard.py` — ÚNICA capa de límites. `fantasy/executor.py` — dry-run / vivo. `fantasy/engine.py` — un run.
- `fantasy/probable.py` — onces probables de futbolfantasy.com (degrada a "desconocido" si falla). `fantasy/notify.py` — Telegram.
- `.github/workflows/run.yml` — cron horario + media hora extra vie–lun. `tests/` — pytest con fixtures anonimizadas.
- `docs/API.md` — endpoints y formas reales de respuesta (verificadas con `raw` el 6/9/2026).

## Reglas de gestión (resumen de config.yaml, perfil agresivo)
1. Puja = valor justo × 1.10; huecos críticos × 1.30. **Nunca ≥ 1.5× valor** (constante `ABSOLUTE_CAP` en código, no configurable).
2. Reserva 0: puede gastar todo el saldo si mejora el once (≥ 0.8 pts esperados/jornada por fichaje).
3. Clausulazo si cláusula ≤ 1.5× valor y aporta ≥ 1.5 pts al once. Subir cláusulas propias hacia 1.8× valor si están < 1.3×.
4. Vender: sobrantes con tendencia negativa, o el peor valor de la plantilla para financiar un fichaje claro. Titulares solo si los listamos nosotros.
5. Alineación: mejor once por puntos esperados (estado, rival, probables). Nunca toca jugadores cuyo partido ya empezó.
6. Todo cambio de reglas va a `config.yaml` con commit; nada de constantes mágicas en la estrategia.

## Reglas de seguridad (NO negociables)
- Las escrituras SOLO pasan por `Executor` + `Guard`. Nunca llamar a métodos de escritura del cliente desde estrategia, scripts sueltos o el chat.
- `FantasyClient(allow_writes=True)` solo en `engine.run_once` (cuando no es dry-run ni kill switch) y en `main.py verify-writes` (interactivo, confirmación por acción).
- Parar todo: variable de repo `KILL_SWITCH=true`. Limitar: `ENABLED_WRITES` (`lineup` / `lineup,market` / `lineup,market,clauses`). `DRY_RUN=true` simula.
- Nunca leer ni imprimir `.env`, `tokens.json` ni el contenido descifrado de `state/auth.enc`. Nunca pedir contraseñas por chat.
- Ritmo humano: ~2 req/s, tope de peticiones por run, sin polling en bucle, sin pujas de último segundo. Ante 429: el run aborta, no reintenta.
- Solo en ligas privadas sin premios (las bases de ligas con premios prohíben automatizar).

## Flujo
- Automático: cron → `python main.py run --live` → commit de `state/` → Telegram.
- Humano (semanal): `/jornada` lee `state/decisions/` y `state/ledger.json`, compara con resultados y propone 1–3 ajustes a `config.yaml`.
- Despliegue por fases con variables de repo: `DRY_RUN=true` → `ENABLED_WRITES=lineup` → `lineup,market` → `lineup,market,clauses`.

## Cuando la API cambie
Es una API no pública y cambia entre temporadas. Si algo devuelve 404/400/500: `python main.py raw`, mirar `data/raw_*/`,
consultar `docs/API.md` y el repo Externoak/LaLigaApp (`src/services/api.js`), y ajustar `client.py`/`state.py` con acceso defensivo.

## Entorno
- Python 3.12+ (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`), ejecutar desde la raíz.
- `.env`: `STATE_KEY` (misma que el secret de GitHub). Login Google: `.venv/bin/python main.py login`.
- Tests: `.venv/bin/python -m pytest -q`. Dry-run local contra la API real: `.venv/bin/python main.py run`.

# LaLiga Fantasy — gestor autónomo

Gestiona solo el equipo de Rafa en LaLiga Fantasy (liga privada) desde GitHub Actions: alineación, pujas, ventas,
clausulazos y subida de cláusulas, con límites duros en código y aviso por Telegram tras cada run.

## Instalación local
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                 # cuenta Google: no hace falta contraseña
.venv/bin/python main.py login       # abre el navegador; pega la URL de vuelta en la terminal
.venv/bin/python main.py ligas       # comprueba que el token funciona
```

## Comandos
```bash
.venv/bin/python main.py run                 # dry-run local contra la API real (no escribe)
.venv/bin/python main.py run --live          # respeta DRY_RUN / ENABLED_WRITES / KILL_SWITCH del entorno
.venv/bin/python main.py raw                 # captura JSON crudos en data/raw_FECHA/
.venv/bin/python main.py verify-writes       # Fase 0: escrituras de verificación una a una (con confirmación)
.venv/bin/python main.py push-token [--set-key]  # cifra el refresh token en state/auth.enc y lo sube al repo
.venv/bin/python main.py informe             # informe Markdown clásico
.venv/bin/python -m pytest -q                # tests sin red
```

## Puesta en marcha en GitHub Actions
1. Repo privado con este código. `gh auth login` en el Mac.
2. `python main.py login` y luego `python main.py push-token --set-key` (genera `STATE_KEY`, la sube como secret y
   commitea `state/auth.enc`).
3. Telegram: crea un bot con @BotFather, pon su token en `.env` como `TELEGRAM_BOT_TOKEN`, escribe `/start` al bot
   y ejecuta `python main.py telegram` (valida el token, detecta tu chat id, envía prueba y sube los secrets).
4. Variables del repo (`gh variable set NOMBRE --body VALOR`):
   - `DRY_RUN`: `true` (fase 1) → `false`
   - `ENABLED_WRITES`: `` → `lineup` → `lineup,market` → `lineup,market,clauses`
   - `KILL_SWITCH`: `false`; ponlo a `true` para parar todo en el siguiente run.
5. Lanza a mano: Actions → fantasy-run → Run workflow (dry_run). Después corre solo cada hora.

## Fases
0. `verify-writes` en local con la app abierta. 1. Dry-run en CI ≥ 4 días. 2. `ENABLED_WRITES=lineup`.
3. `lineup,market`. 4. `lineup,market,clauses`. Marcha atrás en cualquier momento con `KILL_SWITCH=true`.

## Cuando la auth se rompa
El bot avisa por Telegram ("AUTH ROTA"). En el Mac: `python main.py login && python main.py push-token`.

## Notas
- API no pública: puede cambiar sin aviso. Si algo devuelve 404/400, ejecuta `raw` y mira `docs/API.md`.
- `.env`, `tokens.json` y `data/` están en `.gitignore`. `state/auth.enc` va cifrado con `STATE_KEY`.
- Ritmo humano (~2 req/s, tope por run), sin reintentos tras 429. Solo para ligas privadas sin premios.

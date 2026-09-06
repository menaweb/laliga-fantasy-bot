Revisión semanal humana del gestor autónomo. NO ejecuta escrituras: solo analiza y propone.

Pasos:
1. Lee `state/decisions/` de los últimos 7 días, `state/ledger.json` (runs, pujas, listados) y `state/snapshot.json`
   (posición, puntos, saldo, plantilla, once). Si hace falta contexto fresco, ejecuta `.venv/bin/python main.py run`
   (dry-run local) y usa su salida. Nunca leas `.env`, `tokens.json` ni descifres `state/auth.enc`.
2. Resume en 5 líneas: puntos de la jornada vs esperado del once, acciones ejecutadas (OK), acciones bloqueadas por el
   guard y por qué, errores o avisos (auth, 429, scraping caído).
3. Detecta patrones: pujas perdidas sistemáticamente (subir markup), dinero parado (bajar min_gain), titulares con
   probabilidad baja que se alinearon, cláusulas de rivales baratas no aprovechadas, jugadores propios con cláusula
   en riesgo.
4. Propón 1–3 cambios concretos a `config.yaml` con la cifra exacta y una frase de motivo cada uno. Rafa quiere
   cifras, no rangos.
5. Si Rafa aprueba, edita `config.yaml`, ejecuta `.venv/bin/python -m pytest -q` y haz commit + push.
   Recuerda: `ABSOLUTE_CAP = 1.5` no se toca.

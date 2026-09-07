# API LaLiga Fantasy 26/27 (no pública)

Fuente: app oficial, vía github.com/Externoak/LaLigaApp (`src/services/api.js`). Puede cambiar sin aviso.

## Auth (Azure B2C)
- Token: `POST https://login.laliga.es/laligadspprob2c.onmicrosoft.com/oauth2/v2.0/token?p=B2C_1A_ResourceOwnerv2`
  form: `grant_type=password, client_id=af88bcff-1157-40a0-b579-030728aacf0b, scope="openid {client_id} offline_access",
  redirect_uri=authredirect://com.lfp.laligafantasy, username, password, response_type=id_token`
- Refresh: mismo host, `?p=B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN`, `grant_type=refresh_token`.
- La API acepta el `id_token` como `Authorization: Bearer`. Vale ~24h.
- Cuentas Google/Apple (sin contraseña local): Authorization Code + PKCE.
  `GET .../oauth2/v2.0/authorize?p=B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN&client_id=af88bcff-...&response_type=code
  &redirect_uri=authredirect://com.lfp.laligafantasy&scope=openid offline_access&code_challenge=...&code_challenge_method=S256&state=...&nonce=...`
  El navegador redirige a `authredirect://com.lfp.laligafantasy?code=...&state=...`; se pega la URL en la terminal y se canjea:
  `POST .../token?p=B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN` con `grant_type=authorization_code, client_id, code, redirect_uri, code_verifier, scope`.
  (Mismo cliente y política que usa el refresh. El cliente web 6457fa17-... NO admite el redirect nativo.)
- Plan B: sacar el token de la web (fantasy.laliga.com -> DevTools -> Network -> cabecera Authorization)
  y guardarlo con `python main.py token`.
  como `{"bearer": "...", "expires_at": <epoch+86000>}`.

## Base y cabeceras
- `https://fantasy-api.llt-services.com/api` (26/27; el host antiguo `api-fantasy.llt-services.com` quedó congelado en 25/26)
- Prefijo competición: `/v1/competition/1` (1 = LaLiga EA Sports). Añadir `?x-lang=es`.
- POST sin body: NO enviar `Content-Type` (la API responde 400).

## Lectura
| Qué | Ruta |
|---|---|
| Usuario | `GET /v4/user/me` |
| Ligas | `GET {CMP}/leagues` → lista o `{elements|leagues:[...]}` |
| Clasificación | `GET {CMP}/leagues/{leagueId}/standing` (semana: `/standing/{week}`) |
| Actividad | `GET {CMP}/leagues/{leagueId}/activity/{index}` |
| Equipo | `GET {CMP}/leagues/{leagueId}/teams/{teamId}` → `{manager, players:[{playerMaster, buyoutClause, playerTeamId,...}], teamValue}` |
| Dinero | `GET {CMP}/teams/{teamId}/money` |
| Mercado | `GET {CMP}/league/{leagueId}/market` → items `{id, playerMaster, salePrice, expirationDate, discr, sellerTeam, numberOfBids}` |
| Jugadores | `GET {CMP}/players` → `{id, nickname, positionId, teamId, marketValue, points, playerStatus,...}` (sin nombre de club: cruzar con teams-master) |
| Clubes | `GET /v3/teams-master` → `[{id, name, shortName, slug,...}]` |
| Jornada actual | `GET {CMP}/week/current` |
| Calendario | `GET {CMP}/calendar?weekNumber=N` (trae `localId/visitorId`) |
| Alineación | `GET {CMP}/teams/{teamId}/lineup` · formaciones: `GET /v4/teams/lineup/formations?option=free` |
| Detalle jugador | `GET {CMP}/player/{playerId}/league/{leagueId}` |
| Oferta recibida | `GET {CMP}/league/{leagueId}/playerTeam/{playerTeamId}/offer` |

| Actividad | `GET {CMP}/leagues/{leagueId}/activity/{index}` → `[{activityTypeId, user1Id, user2Id?, playerMasterId, amount, weekNumber?, createdAt}]` |
| Alineación por jornada | `GET {CMP}/teams/{teamId}/lineup/week/{week}` |
| Formaciones | `GET /v4/teams/lineup/formations?option=free` → `['5,4,1','5,3,2','4,5,1','4,4,2','4,3,3','3,5,2','3,4,3']` (premium: `option=premium`) |
| Blindaje | `GET {CMP}/league/{leagueId}/player-team/{playerTeamId}/check-shield` (devuelve vacío si no aplica) |

`positionId`: 1 POR, 2 DEF, 3 MED, 4 DEL, 5 ENT. `discr`: `marketPlayerLeague` (vende LaLiga) / `marketPlayerTeam` (vende un mánager).

### Formas reales verificadas (6/9/2026, `python main.py raw`)
- `/players`: los números vienen como **string** (`positionId`, `marketValue`, `lastSeasonPoints`); `points` int; `averagePoints` float;
  `weekPoints: [{weekNumber, points}]`. `playerStatus` ∈ `ok | injured | doubtful | suspended | out_of_league`. Sin nombre completo (solo `nickname`).
- Plantilla (`teams/{id}`): `players[i] = {playerMaster{id, name, nickname, slug, positionId, playerStatus, marketValue, points, averagePoints, team{id,name,slug}},
  buyoutClause, buyoutClauseLockedEndTime, isShielded, playerTeamId, managerId, playerMarket?{id, salePrice, expirationDate, numberOfOffers, directOffer}}`.
  En plantilla el club es `playerMaster.team.id` (no `teamId`).
- Dinero: `{teamMoney, teamInvestment}`. **Verificado 7/9/2026**: `teamMoney` NO baja al pujar; `teamInvestment` = suma de pujas pendientes. Saldo real = `teamMoney - teamInvestment`.
- Vender devuelve el ítem de mercado completo (`id` = marketId, `expirationDate` = ahora + 72h, `numberOfOffers`, `directOffer`). Verificado 7/9/2026.
- Refresh de B2C: el refresh token anterior SIGUE siendo válido tras rotar (verificado 7/9/2026), por eso `state/auth.prev.enc` es un respaldo útil.
- Pujar devuelve `{id, buyerTeam, money, status: pending, createdAt}`; cancelar devuelve lo mismo con `status: canceled`. El ítem de mercado pasa a traer `numberOfBids` y **`bid: {id, money, status}`** con MI puja.
- Mercado: 42 ítems. `numberOfBids` solo en ítems de LaLiga; los de mánager traen `playerTeam{buyoutClause, buyoutClauseLockedEndTime, isShielded, manager}`,
  `sellerTeam{id, manager, teamValue}`, `numberOfOffers`, `directOffer`. `status: on_sale`. Si he pujado, el ítem trae `bid{id, money, status}` (ver arriba).
- Ofertas recibidas: `[{id, money, status: pending, isFromMarket, createdAt, expirationDate}]`. LaLiga hace oferta automática (~0.99× valor) a los listados.
- Jornada: `{weekNumber, isLive, nextWeek, previousWeek, openingWeekDate, closingWeekDate}`.
- Calendario: `[{id, matchDate, localId, visitorId, matchState (1 = pendiente, 4 = en juego, 7 = terminado), localScore, visitorScore}]`.
- Alineación (`GET lineup`): `{formation{goalkeeper[], defender[], midfield[], striker[], coach[], bench{}, tacticalFormation[4,4,2]}, id, team, updatedAt}`;
  cada entrada `{playerMaster, playerTeamId, buyoutClause, playerMarket?}`.
- Liga: `config.features.buyoutClause: true`; `premiumFeatures` (formations, captain, bench, coach…) todas `false` en Liga Tablerillo.
- Cláusula: abierta si `buyoutClauseLockedEndTime` es null o ya pasó. Subir: `factor = 2`, `valueToIncrease = 2 × lo que pagas`.
- `activityTypeId`: 1 compra a mánager · 4 blindaje · 6 ganancia por jornada · 7 alineación incorrecta · 9 nuevo miembro · 31 fichaje a LaLiga · 32 clausulazo · 33 venta.

## Escritura (bloqueada en client.py salvo allow_writes=True)
| Acción | Ruta | Body |
|---|---|---|
| Pujar (jugador de LaLiga, `marketPlayerLeague`) | `POST {CMP}/league/{leagueId}/market/{marketId}/bid` | `{"money": N}` |
| Ofertar (jugador de un mánager, `marketPlayerTeam`) | `POST {CMP}/league/{leagueId}/market/{marketId}/offer` | `{"money": N}` (usar `/bid` en estos devuelve 404, verificado 7/9/2026) |
| Modificar oferta | `PUT .../market/{marketId}/offer/{offerId}` | `{"money": N}` |
| Modificar puja | `PUT .../market/{marketId}/bid/{bidId}` | `{"money": N}` |
| Cancelar puja | `DELETE .../market/{marketId}/bid/{bidId}/cancel` | — |
| Vender | `POST {CMP}/league/{leagueId}/market/sell` | `{"playerId": playerTeamId, "salePrice"}` (**playerTeamId**, no el id del jugador; si no: 400 "player is not in your team anymore") |
| Retirar del mercado | `DELETE .../market/{marketId}/delete` | — (responde 204 sin cuerpo) |
| Aceptar oferta | `POST .../market/{marketId}/offer/{offerId}/accept` | `{"offerMoney": N}` (obligatorio) |
| Rechazar oferta | `POST .../market/{marketId}/offer/{offerId}/reject` | sin body |
| Alineación | `PUT {CMP}/teams/{teamId}/lineup` | `{"goalkeeper": playerTeamId, "defender": [ptid…], "midfield": [ptid…], "striker": [ptid…], "tactical_formation": [4,4,2]}` |
| Cancelar oferta | `DELETE .../market/{marketId}/offer/{offerId}/cancel` | — |
| Recompensa diaria | `POST {CMP}/league/{leagueId}/team/daily-reward` | exige `{"teamId", "rewardedAdType", "rewardedAd"}`; el servidor valida `rewardedAd` ("RewardedAd not valid", 050.01.01) con cualquier valor probado (7/9/2026): está ligado al anuncio de la app. Comprobar: `GET {CMP}/league/{leagueId}/team/{teamId}/check-daily-reward` → `{teamId, dailyRewardsRedeemed}` |
| Oferta directa | `POST {CMP}/league/{leagueId}/market/direct-offer` | `{"playerId", "money"}` |
| Subir cláusula | `PUT {CMP}/league/{leagueId}/buyout/player` | `{"playerId": playerTeamId, "factor": 2, "valueToIncrease": 2×pago}` |
| Pagar cláusula | `POST {CMP}/league/{leagueId}/buyout/{playerTeamId}/pay` | `{"buyoutClauseToPay": N}` (playerTeamId del jugador en la plantilla rival) |

Mínimo de puja = `max(marketValue, salePrice)`.

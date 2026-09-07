"""
Cliente de la API no pública de LaLiga Fantasy, temporada 26/27.
Rutas tomadas de la app oficial (via github.com/Externoak/LaLigaApp).

Los métodos de escritura están bloqueados por `allow_writes=False`. En el modo
autónomo solo `engine` los desbloquea, y siempre detrás de `guard`/`executor`.
"""
import time
import requests

BASE = "https://fantasy-api.llt-services.com/api"
COMPETITION_ID = 1  # LaLiga EA Sports
CMP = f"/v1/competition/{COMPETITION_ID}"

POSITIONS = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL", 5: "ENT"}


class ApiError(Exception):
    pass


class FantasyClient:
    def __init__(self, bearer: str, allow_writes: bool = False, min_interval: float = 0.6,
                 max_requests: int | None = None):
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {bearer}",
            "x-lang": "es",
            "Accept": "application/json",
            "Origin": "https://fantasy.laliga.com",
            "Referer": "https://fantasy.laliga.com/",
        })
        self.allow_writes = allow_writes
        self.min_interval = min_interval  # ritmo humano: no más de ~2 req/s
        self.max_requests = max_requests  # red de seguridad contra bucles (None = sin tope)
        self.request_count = 0
        self._last = 0.0

    # ---------- núcleo ----------
    def _req(self, method: str, path: str, json=None):
        if self.max_requests is not None and self.request_count >= self.max_requests:
            raise ApiError(f"Tope de {self.max_requests} peticiones por run alcanzado ({method} {path})")
        self.request_count += 1
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = f"{BASE}{path}{'&' if '?' in path else '?'}x-lang=es"
        headers = {}
        if json is not None:
            headers["Content-Type"] = "application/json"
        r = self.s.request(method, url, json=json, headers=headers, timeout=20)
        self._last = time.time()
        if r.status_code == 429:
            raise ApiError("429: demasiadas peticiones, espera unos minutos")
        if not r.ok:
            raise ApiError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:200]}")
        if not r.content:
            return None
        ct = r.headers.get("content-type", "")
        return r.json() if "json" in ct else r.text

    def _get(self, path):
        return self._req("GET", path)

    def _write(self, method, path, json=None):
        if not self.allow_writes:
            raise ApiError(f"Escritura bloqueada ({method} {path}). Activa allow_writes=True a propósito.")
        return self._req(method, path, json=json)

    @staticmethod
    def _unwrap(data, *keys):
        """La API 26/27 a veces envuelve listas en {elements:[...]} o {leagues:[...]}."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("elements", *keys):
                if isinstance(data.get(k), list):
                    return data[k]
        return data

    # ---------- lectura ----------
    def me(self):
        return self._get("/v4/user/me")

    def leagues(self):
        return self._unwrap(self._get(f"{CMP}/leagues"), "leagues")

    def standing(self, league_id):
        return self._unwrap(self._get(f"{CMP}/leagues/{league_id}/standing"))

    def team(self, league_id, team_id):
        return self._get(f"{CMP}/leagues/{league_id}/teams/{team_id}")

    def money(self, team_id):
        return self._get(f"{CMP}/teams/{team_id}/money")

    def market(self, league_id):
        return self._unwrap(self._get(f"{CMP}/league/{league_id}/market"))

    def players(self):
        return self._unwrap(self._get(f"{CMP}/players"))

    def teams_master(self):
        data = self._get("/v3/teams-master")
        return self._unwrap(data, "teams")

    def current_week(self):
        return self._get(f"{CMP}/week/current")

    def calendar(self, week):
        return self._unwrap(self._get(f"{CMP}/calendar?weekNumber={week}"))

    def lineup(self, team_id):
        return self._get(f"{CMP}/teams/{team_id}/lineup")

    def player_detail(self, player_id, league_id):
        return self._get(f"{CMP}/player/{player_id}/league/{league_id}")

    def standing_week(self, league_id, week):
        return self._unwrap(self._get(f"{CMP}/leagues/{league_id}/standing/{week}"))

    def activity(self, league_id, index=0):
        return self._unwrap(self._get(f"{CMP}/leagues/{league_id}/activity/{index}"))

    def lineup_week(self, team_id, week):
        return self._get(f"{CMP}/teams/{team_id}/lineup/week/{week}")

    def formations(self, option="free"):
        return self._unwrap(self._get(f"/v4/teams/lineup/formations?option={option}"))

    def received_offers(self, league_id, player_team_id):
        return self._get(f"{CMP}/league/{league_id}/playerTeam/{player_team_id}/offer")

    def check_daily_reward(self, league_id, team_id):
        return self._get(f"{CMP}/league/{league_id}/team/{team_id}/check-daily-reward")

    def check_shield(self, league_id, player_team_id):
        return self._get(f"{CMP}/league/{league_id}/player-team/{player_team_id}/check-shield")

    # ---------- escritura (bloqueada por defecto) ----------
    def bid(self, league_id, market_id, money):
        return self._write("POST", f"{CMP}/league/{league_id}/market/{market_id}/bid", {"money": money})

    def offer(self, league_id, market_id, money):
        """Oferta por un jugador que vende OTRO mánager (discr marketPlayerTeam). Los de LaLiga van por bid()."""
        return self._write("POST", f"{CMP}/league/{league_id}/market/{market_id}/offer", {"money": money})

    def modify_offer(self, league_id, market_id, offer_id, money):
        return self._write("PUT", f"{CMP}/league/{league_id}/market/{market_id}/offer/{offer_id}", {"money": money})

    def modify_bid(self, league_id, market_id, bid_id, money):
        return self._write("PUT", f"{CMP}/league/{league_id}/market/{market_id}/bid/{bid_id}", {"money": money})

    def cancel_bid(self, league_id, market_id, bid_id):
        return self._write("DELETE", f"{CMP}/league/{league_id}/market/{market_id}/bid/{bid_id}/cancel")

    def sell(self, league_id, player_team_id, sale_price):
        # OJO: la API espera el playerTeamId (id del jugador EN TU EQUIPO), no el id del jugador.
        return self._write("POST", f"{CMP}/league/{league_id}/market/sell",
                           {"playerId": player_team_id, "salePrice": sale_price})

    def withdraw(self, league_id, market_id):
        return self._write("DELETE", f"{CMP}/league/{league_id}/market/{market_id}/delete")

    def accept_offer(self, league_id, market_id, offer_id, offer_money):
        return self._write("POST", f"{CMP}/league/{league_id}/market/{market_id}/offer/{offer_id}/accept",
                           {"offerMoney": offer_money})

    def reject_offer(self, league_id, market_id, offer_id):
        return self._write("POST", f"{CMP}/league/{league_id}/market/{market_id}/offer/{offer_id}/reject")

    def set_lineup(self, team_id, lineup_payload):
        return self._write("PUT", f"{CMP}/teams/{team_id}/lineup", lineup_payload)

    def claim_daily_reward(self, league_id, team_id, body=None):
        """Recompensa diaria (100.000 €). La API exige rewardedAdType + rewardedAd válidos (ligados a un anuncio).
        El body se toma de config.yaml (reward.*) cuando se conozca; verify-writes prueba variantes."""
        return self._write("POST", f"{CMP}/league/{league_id}/team/daily-reward", body or {"teamId": int(team_id)})

    def direct_offer(self, league_id, player_id, money):
        return self._write("POST", f"{CMP}/league/{league_id}/market/direct-offer",
                           {"playerId": player_id, "money": money})

    def cancel_offer(self, league_id, market_id, offer_id):
        return self._write("DELETE", f"{CMP}/league/{league_id}/market/{market_id}/offer/{offer_id}/cancel")

    def pay_clause(self, league_id, player_team_id, amount):
        # playerTeamId del jugador en la plantilla RIVAL
        return self._write("POST", f"{CMP}/league/{league_id}/buyout/{player_team_id}/pay",
                           {"buyoutClauseToPay": amount})

    def raise_clause(self, league_id, player_team_id, factor, value_to_increase):
        # playerTeamId del jugador en MI plantilla; valueToIncrease = factor x lo que se paga
        return self._write("PUT", f"{CMP}/league/{league_id}/buyout/player",
                           {"playerId": player_team_id, "factor": factor, "valueToIncrease": value_to_increase})

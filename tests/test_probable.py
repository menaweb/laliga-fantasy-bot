import os

from fantasy.probable import parse_team_html, match_players
from tests.conftest import FIX


def test_parse_and_match(snap):
    html = open(os.path.join(FIX, "futbolfantasy_real-sociedad.html"), encoding="utf-8").read()
    rows = parse_team_html(html)
    assert len(rows) >= 22 and sum(r["status"] == "starter" for r in rows) == 11
    club = [p for p in snap.players.values() if p["teamId"] == "16" and p["playerStatus"] != "out_of_league"]
    m = match_players(rows, club)
    assert len(m) >= 20
    oy = next(p for p in club if p["nickname"] == "Oyarzabal")
    assert m[oy["id"]]["status"] == "starter" and m[oy["id"]]["pct"] == 70


def test_broken_html_returns_nothing():
    assert parse_team_html("<html><body>nada</body></html>") == []

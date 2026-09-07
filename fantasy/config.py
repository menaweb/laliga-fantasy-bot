"""Carga config.yaml y aplica overrides de entorno. Valida los límites duros."""
import os
import yaml

ABSOLUTE_CAP = 1.5  # nunca pagar >= 1.5x valor de mercado, pase lo que pase en config.yaml
POS_NAMES = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL", 5: "ENT"}
WRITE_GROUPS = ("lineup", "market", "clauses", "reward")


class Section(dict):
    """dict con acceso por atributo, recursivo."""
    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError:
            raise AttributeError(k)
        return Section(v) if isinstance(v, dict) and not isinstance(v, Section) else v


def _env_bool(name, default=False):
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config(path="config.yaml") -> Section:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = Section(raw)
    cfg["league_id"] = os.getenv("LALIGA_LEAGUE_ID") or str(cfg.get("league_id") or "")
    cfg["dry_run"] = _env_bool("DRY_RUN", default=True)
    cfg["kill_switch"] = _env_bool("KILL_SWITCH", default=False)
    groups = os.getenv("ENABLED_WRITES", "")
    cfg["enabled_writes"] = tuple(g.strip() for g in groups.split(",") if g.strip() in WRITE_GROUPS)
    cfg["state_dir"] = os.getenv("STATE_DIR", "state")
    validate(cfg)
    return cfg


def validate(cfg: Section) -> None:
    b, c = cfg.bids, cfg.clauses
    if b.hard_cap_ratio >= ABSOLUTE_CAP:
        raise ValueError(f"bids.hard_cap_ratio debe ser < {ABSOLUTE_CAP}")
    if b.markup_critical > b.hard_cap_ratio or b.markup_default > b.markup_critical:
        raise ValueError("bids: se requiere markup_default <= markup_critical <= hard_cap_ratio")
    if c.pay_cap_ratio > ABSOLUTE_CAP:
        raise ValueError(f"clauses.pay_cap_ratio debe ser <= {ABSOLUTE_CAP}")
    if cfg.money.reserve < 0 or cfg.money.max_spend_per_run <= 0:
        raise ValueError("money: reserve >= 0 y max_spend_per_run > 0")
    if cfg.run.max_actions_per_run < 1 or cfg.run.max_requests_per_run < 20:
        raise ValueError("run: max_actions_per_run >= 1 y max_requests_per_run >= 20")
    if not cfg.league_id:
        raise ValueError("league_id vacío (config.yaml o LALIGA_LEAGUE_ID)")

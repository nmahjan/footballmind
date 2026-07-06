"""
FootballMind -- production model: train, store, load, deploy.

Bridges the backtest to the live app. select_and_deploy() runs the parameter
sweep, retrains the hybrid on ALL data with the winning config, and stores it;
predict_match loads it via load_hybrid() at request time.

The fitted hybrid is plain floats + small dicts, so it serializes to JSONB --
no pickle, inspectable in the database.

Storage: the model_artifacts table, applied by migrations/004_model_artifacts.sql.
"""

import json

import numpy as np

from footballmind_dixoncoles import DixonColes, fit_from_db
from footballmind_backtest import HybridLambdas, sweep_from_db


# ----------------------------------------------------------------------
# (De)serialization  -- hybrid <-> JSON-able dict
# ----------------------------------------------------------------------
def _serialize_dc(dc):
    return {
        "attack":     dc.attack.tolist(),
        "defence":    dc.defence.tolist(),
        "home_adv":   dc.home_adv,
        "rho":        dc.rho,
        "intercept":  dc.intercept,
        "team_index": {str(k): v for k, v in dc.team_index.items()},
    }


def _deserialize_dc(d):
    dc = DixonColes()
    dc.attack = np.array(d["attack"])
    dc.defence = np.array(d["defence"])
    dc.home_adv = d["home_adv"]
    dc.rho = d["rho"]
    dc.intercept = d["intercept"]
    dc.team_index = {int(k): v for k, v in d["team_index"].items()}   # JSON keys are strings
    dc.index_team = {v: k for k, v in dc.team_index.items()}
    return dc


def serialize_hybrid(h):
    return {
        "dc":               _serialize_dc(h.dc),
        "elo":              {str(k): v for k, v in h.elo.items()},
        "counts":           {str(k): v for k, v in h.counts.items()},
        "full_credibility": h.full,
    }


def deserialize_hybrid(d):
    return HybridLambdas(
        _deserialize_dc(d["dc"]),
        {int(k): v for k, v in d["elo"].items()},
        {int(k): v for k, v in d["counts"].items()},
        d["full_credibility"])


# ----------------------------------------------------------------------
# DB helpers
# ----------------------------------------------------------------------
def _read_elo(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT team_id, rating FROM team_ratings")
        return {tid: rating for tid, rating in cur.fetchall()}


def _match_counts(conn, edition_ids):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT team_id, count(*) FROM ("
            "  SELECT home_team_id AS team_id FROM matches "
            "    WHERE edition_id = ANY(%s) AND home_goals IS NOT NULL "
            "  UNION ALL "
            "  SELECT away_team_id FROM matches "
            "    WHERE edition_id = ANY(%s) AND home_goals IS NOT NULL"
            ") s GROUP BY team_id", (list(edition_ids), list(edition_ids)))
        return {tid: n for tid, n in cur.fetchall()}


# ----------------------------------------------------------------------
# Train / store / load
# ----------------------------------------------------------------------
def train_and_store(conn, edition_ids, half_life_days, full_credibility,
                    backtest_rps=None, name="production_hybrid"):
    """Refit the hybrid on all data with the chosen config and persist it.
    Elo comes from team_ratings (kept current by the sync job)."""
    dc = fit_from_db(conn, edition_ids, half_life_days)
    hybrid = HybridLambdas(dc, _read_elo(conn),
                           _match_counts(conn, edition_ids), full_credibility)
    payload = json.dumps(serialize_hybrid(hybrid))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO model_artifacts (name, artifact, half_life_days, "
            " full_credibility, backtest_rps) VALUES (%s, %s::jsonb, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET artifact = EXCLUDED.artifact, "
            "  half_life_days = EXCLUDED.half_life_days, "
            "  full_credibility = EXCLUDED.full_credibility, "
            "  backtest_rps = EXCLUDED.backtest_rps, trained_at = now()",
            (name, payload, half_life_days, full_credibility, backtest_rps))
    conn.commit()
    _CACHE[name] = hybrid
    return hybrid


_CACHE = {}


def load_hybrid(conn, name="production_hybrid", use_cache=True):
    """Return the deployed hybrid, or None if no model has been trained yet
    (predict_match then falls back to pure Elo)."""
    if use_cache and name in _CACHE:
        return _CACHE[name]
    with conn.cursor() as cur:
        cur.execute("SELECT artifact FROM model_artifacts WHERE name = %s", (name,))
        row = cur.fetchone()
    if row is None:
        return None
    artifact = row[0]
    if isinstance(artifact, str):           # some drivers hand back raw text
        artifact = json.loads(artifact)
    hybrid = deserialize_hybrid(artifact)
    _CACHE[name] = hybrid
    return hybrid


def select_and_deploy(conn, edition_ids, test_start, half_lives=(90, 180, 365),
                      credibilities=(5, 10, 20), refit_every_days=14,
                      importance="league", name="production_hybrid",
                      min_history=60,
                      default_half_life=180, default_credibility=10):
    """The capstone: sweep -> pick lowest-RPS config -> retrain on all data ->
    store -> warm the cache. Returns the full sweep result for inspection."""
    try:
        result = sweep_from_db(conn, edition_ids, test_start, half_lives=half_lives,
                               credibilities=credibilities,
                               refit_every_days=refit_every_days,
                               importance=importance, min_history=min_history)
        best = result["best"]
    except ValueError as exc:
        # Early tournaments (e.g. WC group stage) may lack pre-test training folds.
        best = {"half_life_days": default_half_life,
                "full_credibility": default_credibility,
                "mean_rps": None, "n": 0}
        result = {"best": best, "grid": [], "target": "hybrid",
                  "backtest_skipped": str(exc)}
    train_and_store(conn, edition_ids, best["half_life_days"],
                    best["full_credibility"], backtest_rps=best["mean_rps"], name=name)
    return result

"""
FootballMind -- cold-start hybrid + RPS backtest harness.

Two pieces:

1. HybridLambdas -- blends Dixon-Coles with Elo per match. A team with plenty
   of matches is trusted fully to Dixon-Coles; a data-poor team (e.g. a World
   Cup side with few games) is pulled toward its Elo estimate. The blend is a
   credibility-weighted geometric mean in log space, so it degrades smoothly
   instead of falling off a cliff at a hard cutoff.

2. backtest_matches -- walk-forward evaluation with NO lookahead: for each test
   fold, fit only on matches strictly before it, predict, and score with the
   Ranked Probability Score (RPS), the proper scoring rule for football's
   ordered home/draw/away outcome. Lower RPS = better. Compares elo-only,
   dixon-coles-only, hybrid, and a base-rate baseline so you can see what
   actually helps.
"""

import math
from datetime import timedelta

from footballmind_predict import predict
from footballmind_elo import update_elo, ratings_to_lambdas
from footballmind_dixoncoles import DixonColes


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------
def rps(probs, outcome_idx):
    """Ranked Probability Score for one ordered 3-outcome forecast.
    probs = [P(home), P(draw), P(away)]; outcome_idx in {0,1,2}."""
    obs = [0, 0, 0]
    obs[outcome_idx] = 1
    cum_p = cum_o = total = 0.0
    for k in range(len(probs) - 1):          # r-1 cumulative terms
        cum_p += probs[k]
        cum_o += obs[k]
        total += (cum_p - cum_o) ** 2
    return total / (len(probs) - 1)


def result_index(home_goals, away_goals):
    if home_goals > away_goals:
        return 0                              # home win
    return 1 if home_goals == away_goals else 2   # draw / away win


# ----------------------------------------------------------------------
# Cold-start hybrid
# ----------------------------------------------------------------------
class HybridLambdas:
    def __init__(self, dc_model, elo_ratings, match_counts, full_credibility=10):
        self.dc = dc_model
        self.elo = elo_ratings
        self.counts = match_counts
        self.full = full_credibility          # matches needed to fully trust DC

    def credibility(self, team_id):
        return min(1.0, self.counts.get(team_id, 0) / self.full)

    def expected_goals(self, home_id, away_id, neutral=False):
        elo_lh, elo_la = ratings_to_lambdas(
            self.elo.get(home_id, 1500.0), self.elo.get(away_id, 1500.0), neutral)
        # pure Elo if either team was never fit by Dixon-Coles
        if home_id not in self.dc.team_index or away_id not in self.dc.team_index:
            return elo_lh, elo_la
        w = min(self.credibility(home_id), self.credibility(away_id))
        if w <= 0:
            return elo_lh, elo_la
        dc_lh, dc_la = self.dc.expected_goals(home_id, away_id, neutral)
        # geometric blend: w=1 -> all Dixon-Coles, w=0 -> all Elo
        lh = math.exp(w * math.log(dc_lh) + (1 - w) * math.log(elo_lh))
        la = math.exp(w * math.log(dc_la) + (1 - w) * math.log(elo_la))
        return lh, la


# ----------------------------------------------------------------------
# Fold helpers (operate on plain match dicts so they are DB-independent)
# match dict: {home, away, hg, ag, date, neutral}
# ----------------------------------------------------------------------
def _elo_replay(train, importance="league"):
    ratings = {}
    for m in sorted(train, key=lambda r: r["date"]):
        h = ratings.get(m["home"], 1500.0)
        a = ratings.get(m["away"], 1500.0)
        nh, na = update_elo(h, a, m["hg"], m["ag"], importance, m.get("neutral", False))
        ratings[m["home"]], ratings[m["away"]] = nh, na
    return ratings


def _counts(train):
    c = {}
    for m in train:
        c[m["home"]] = c.get(m["home"], 0) + 1
        c[m["away"]] = c.get(m["away"], 0) + 1
    return c


def _fit_dc(train, cutoff, half_life_days):
    teams = sorted({m["home"] for m in train} | {m["away"] for m in train})
    index = {t: k for k, t in enumerate(teams)}
    xi = math.log(2) / half_life_days
    model = DixonColes().fit(
        [index[m["home"]] for m in train],
        [index[m["away"]] for m in train],
        [m["hg"] for m in train],
        [m["ag"] for m in train],
        [math.exp(-xi * max((cutoff - m["date"]).days, 0)) for m in train],
        len(teams))
    model.team_index = index
    model.index_team = {v: k for k, v in index.items()}
    return model


def _score(acc, out, outcome_idx):
    probs = [out["home_win_prob"], out["draw_prob"], out["away_win_prob"]]
    acc[0] += rps(probs, outcome_idx)
    acc[1] += 1


# ----------------------------------------------------------------------
# Walk-forward backtest
# ----------------------------------------------------------------------
def _memo(cache, key, fn):
    """Return cache[key], computing via fn() on miss. cache=None disables memoization."""
    if cache is None:
        return fn()
    if key not in cache:
        cache[key] = fn()
    return cache[key]


def backtest_matches(matches, test_start, half_life_days=180,
                     full_credibility=10, refit_every_days=14,
                     importance="league", min_history=60,
                     _elo_cache=None, _counts_cache=None, _dc_cache=None):
    # The _*_cache args let sweep() share per-fold work across grid cells. Elo replay
    # and match counts depend only on the fold (not on half_life/credibility); the DC
    # fit depends on (fold, half_life) but not credibility. Passing dicts here computes
    # each once instead of once per grid cell -- identical results, far less scipy work.
    matches = sorted(matches, key=lambda m: m["date"])
    test = [m for m in matches if m["date"] >= test_start]
    if not test:
        raise ValueError("no test matches on/after test_start")
    last_date = max(m["date"] for m in matches)

    # base rates (typical football): a fixed, model-free reference
    base = {"home_win_prob": 0.44, "draw_prob": 0.27, "away_win_prob": 0.29}
    agg = {c: [0.0, 0] for c in ("elo", "dixon_coles", "hybrid", "baseline")}

    fold_start = test_start
    while fold_start <= last_date:
        fold_end = fold_start + timedelta(days=refit_every_days)
        fold = [m for m in test if fold_start <= m["date"] < fold_end]
        train = [m for m in matches if m["date"] < fold_start]
        if fold and len(train) >= min_history:
            elo = _memo(_elo_cache, (fold_start, importance),
                        lambda: _elo_replay(train, importance))
            dc = _memo(_dc_cache, (fold_start, half_life_days),
                       lambda: _fit_dc(train, fold_start, half_life_days))
            counts = _memo(_counts_cache, fold_start, lambda: _counts(train))
            hybrid = HybridLambdas(dc, elo, counts, full_credibility)

            for m in fold:
                oi = result_index(m["hg"], m["ag"])
                neutral = m.get("neutral", False)

                lh, la = ratings_to_lambdas(elo.get(m["home"], 1500.0),
                                            elo.get(m["away"], 1500.0), neutral)
                _score(agg["elo"], predict(lh, la, "regular_season"), oi)

                if m["home"] in dc.team_index and m["away"] in dc.team_index:
                    lh, la = dc.expected_goals(m["home"], m["away"], neutral)
                _score(agg["dixon_coles"], predict(lh, la, "regular_season"), oi)

                lh, la = hybrid.expected_goals(m["home"], m["away"], neutral)
                _score(agg["hybrid"], predict(lh, la, "regular_season"), oi)

                _score(agg["baseline"], base, oi)
        fold_start = fold_end

    return {c: {"mean_rps": (s / n if n else None), "n": n} for c, (s, n) in agg.items()}


def backtest_from_db(conn, edition_ids, test_start, **kwargs):
    return backtest_matches(_load_matches(conn, edition_ids), test_start, **kwargs)


# ----------------------------------------------------------------------
# Parameter sweep: grid over half-life x credibility, ranked by RPS
# ----------------------------------------------------------------------
def sweep(matches, test_start, half_lives=(90, 180, 365),
          credibilities=(5, 10, 20), refit_every_days=14,
          importance="league", target="hybrid", min_history=60):
    """Backtest every (half_life_days, full_credibility) combination and rank
    them by the target model's mean RPS (lowest first). Returns the best cell
    plus the full grid so you can see the whole surface."""
    grid = []
    # Shared across the whole grid: elo-replay + counts are identical for every cell
    # of a given fold, and the DC fit is identical across credibilities for a given
    # (fold, half_life). Compute each once here instead of per cell.
    elo_cache: dict = {}
    counts_cache: dict = {}
    dc_cache: dict = {}
    for hl in half_lives:
        for fc in credibilities:
            res = backtest_matches(matches, test_start, half_life_days=hl,
                                   full_credibility=fc,
                                   refit_every_days=refit_every_days,
                                   importance=importance,
                                   min_history=min_history,
                                   _elo_cache=elo_cache, _counts_cache=counts_cache,
                                   _dc_cache=dc_cache)
            grid.append({"half_life_days": hl, "full_credibility": fc,
                         "mean_rps": res[target]["mean_rps"], "n": res[target]["n"]})
    viable = [r for r in grid if r["mean_rps"] is not None]
    if not viable:
        raise ValueError("no backtest folds scored (insufficient match history)")
    viable.sort(key=lambda r: r["mean_rps"])
    return {"best": viable[0], "grid": grid, "target": target}


def _load_matches(conn, edition_ids):
    from footballmind_db import release_transaction

    with conn.cursor() as cur:
        cur.execute(
            "SELECT home_team_id, away_team_id, home_goals, away_goals, "
            "       match_date, stage FROM matches "
            "WHERE edition_id = ANY(%s) AND home_goals IS NOT NULL "
            "ORDER BY match_date", (list(edition_ids),))
        rows = cur.fetchall()
    release_transaction(conn)
    return [{"home": r[0], "away": r[1], "hg": r[2], "ag": r[3],
             "date": r[4].date(), "neutral": r[5] != "regular_season"}
            for r in rows]


def sweep_from_db(conn, edition_ids, test_start, **kwargs):
    return sweep(_load_matches(conn, edition_ids), test_start, **kwargs)

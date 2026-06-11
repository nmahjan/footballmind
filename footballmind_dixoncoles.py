"""
FootballMind -- Dixon-Coles fitter.

Time-weighted maximum-likelihood fit of per-team attack & defence ratings, a
home-advantage term, and the Dixon-Coles low-score dependence parameter rho.
Produces the lambda_home / lambda_away that feed straight into predict().

Model (log-linear form):
    log lambda_home = intercept + home_adv + attack[i] - defence[j]
    log lambda_away = intercept            + attack[j] - defence[i]

A higher attack -> scores more; a higher defence -> concedes fewer. The
low-score correction tau(x, y) adjusts the four cells {0,1}x{0,1} where the
independent-Poisson assumption is weakest (notably 0-0 and 1-1 draws). Each
match is weighted by exp(-xi * days_ago) so recent form counts more.
"""

from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson


def _log_tau(hg, ag, lam, mu, rho, eps=1e-10):
    """Dixon-Coles low-score dependence correction, in log space."""
    tau = np.ones_like(lam)
    m00 = (hg == 0) & (ag == 0); tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
    m01 = (hg == 0) & (ag == 1); tau[m01] = 1.0 + lam[m01] * rho
    m10 = (hg == 1) & (ag == 0); tau[m10] = 1.0 + mu[m10] * rho
    m11 = (hg == 1) & (ag == 1); tau[m11] = 1.0 - rho
    return np.log(np.clip(tau, eps, None))


class DixonColes:
    def __init__(self):
        self.attack = self.defence = None
        self.home_adv = self.rho = self.intercept = 0.0
        self.team_index = {}     # team_id -> parameter position
        self.index_team = {}     # parameter position -> team_id
        self.converged = False

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------
    def fit(self, home_idx, away_idx, home_goals, away_goals, weights, n_teams):
        home_idx = np.asarray(home_idx); away_idx = np.asarray(away_idx)
        hg = np.asarray(home_goals, float); ag = np.asarray(away_goals, float)
        w = np.asarray(weights, float)

        def neg_log_likelihood(params):
            attack  = params[:n_teams]
            defence = params[n_teams:2 * n_teams]
            home_adv, rho = params[2 * n_teams], params[2 * n_teams + 1]
            lam = np.exp(home_adv + attack[home_idx] - defence[away_idx])
            mu  = np.exp(           attack[away_idx] - defence[home_idx])
            ll = (_log_tau(hg, ag, lam, mu, rho)
                  + poisson.logpmf(hg, lam)
                  + poisson.logpmf(ag, mu))
            return -np.sum(w * ll)

        x0 = np.concatenate([np.zeros(2 * n_teams), [0.25, -0.10]])
        bounds = [(-3, 3)] * (2 * n_teams) + [(-1, 1), (-0.2, 0.2)]
        res = minimize(neg_log_likelihood, x0, method="L-BFGS-B", bounds=bounds)

        attack  = res.x[:n_teams]
        defence = res.x[n_teams:2 * n_teams]
        # Normalise to mean-zero so ratings are interpretable. Predictions are
        # unchanged: the shift is absorbed into the intercept.
        a_bar, d_bar = attack.mean(), defence.mean()
        self.attack    = attack - a_bar
        self.defence   = defence - d_bar
        self.intercept = a_bar - d_bar
        self.home_adv  = float(res.x[2 * n_teams])
        self.rho       = float(res.x[2 * n_teams + 1])
        self.converged = bool(res.success)
        return self

    # ------------------------------------------------------------------
    # Prediction -- the bridge into predict()
    # ------------------------------------------------------------------
    def expected_goals(self, home_team_id, away_team_id, neutral=False):
        i = self.team_index[home_team_id]
        j = self.team_index[away_team_id]
        home = 0.0 if neutral else self.home_adv
        lam = np.exp(self.intercept + home + self.attack[i] - self.defence[j])
        mu  = np.exp(self.intercept        + self.attack[j] - self.defence[i])
        return float(lam), float(mu)


# ----------------------------------------------------------------------
# Loading training data from the schema + exponential time weights
# ----------------------------------------------------------------------
def load_training_data(conn, edition_ids, half_life_days=180, as_of=None):
    as_of = as_of or date.today()
    xi = np.log(2) / half_life_days            # weight halves every half_life_days
    with conn.cursor() as cur:
        cur.execute(
            "SELECT home_team_id, away_team_id, home_goals, away_goals, match_date "
            "FROM matches WHERE edition_id = ANY(%s) AND home_goals IS NOT NULL "
            "ORDER BY match_date", (list(edition_ids),))
        rows = cur.fetchall()
    teams = sorted({r[0] for r in rows} | {r[1] for r in rows})
    index = {t: k for k, t in enumerate(teams)}
    days_ago = np.array([max((as_of - r[4].date()).days, 0) for r in rows], float)
    return {
        "home_idx":   [index[r[0]] for r in rows],
        "away_idx":   [index[r[1]] for r in rows],
        "home_goals": [r[2] for r in rows],
        "away_goals": [r[3] for r in rows],
        "weights":    np.exp(-xi * days_ago),
        "teams":      teams,
        "index":      index,
    }


def fit_from_db(conn, edition_ids, half_life_days=180):
    d = load_training_data(conn, edition_ids, half_life_days)
    model = DixonColes().fit(d["home_idx"], d["away_idx"], d["home_goals"],
                             d["away_goals"], d["weights"], len(d["teams"]))
    model.team_index = d["index"]
    model.index_team = {v: k for k, v in d["index"].items()}
    return model

# Hook-up: in footballmind_mcp_predict.py swap the Elo line
#     lam_h, lam_a = ratings_to_lambdas(home_elo, away_elo, neutral)
# for
#     lam_h, lam_a = model.expected_goals(home_id, away_id, neutral)
# Keep Elo as the cold-start fallback when a team has too few matches to fit.

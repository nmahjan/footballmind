"""
FootballMind -- World Cup 2026 outlook (Monte Carlo).

Simulates the tournament many times from current team ratings and prints
P(champion) per team. Group stage uses the real fixture list (with group
assignments from the API); each match is sampled from the Poisson goal model
at the Elo-implied lambdas. The 48-team format advances 12 group winners +
12 runners-up + 8 best third-placed teams to a round of 32.

Approximation: the knockout bracket uses a seeded random draw (group winners
face runners-up/thirds, same-group rematches avoided in the R32) instead of
FIFA's fixed slot map -- a small distortion that barely moves P(champion).

Usage: python footballmind_wc_outlook.py [n_sims]
"""

import os
import sys
from collections import Counter, defaultdict

import numpy as np

import footballmind_db  # noqa: F401  (loads .env)
from footballmind_db import get_connection
from footballmind_elo import ratings_to_lambdas, expected_score
from footballmind_sync import TokenBucket, FootballDataClient


def load_inputs():
    client = FootballDataClient(os.environ["FOOTBALL_DATA_API_KEY"], TokenBucket(10))
    api_matches = client._get("/competitions/WC/matches").get("matches", [])
    group_fixtures = [
        (m["homeTeam"]["name"], m["awayTeam"]["name"], m["group"])
        for m in api_matches
        if m.get("group") and m["homeTeam"].get("name") and m["awayTeam"].get("name")
    ]
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT t.name, r.rating FROM team_ratings r "
                    "JOIN teams t ON t.id = r.team_id WHERE t.type = 'national'")
        elo = dict(cur.fetchall())
    return group_fixtures, elo


def simulate(group_fixtures, elo, n_sims=10000, seed=7):
    rng = np.random.default_rng(seed)
    titles = Counter()
    last16 = Counter()

    groups = defaultdict(set)
    for h, a, g in group_fixtures:
        groups[g].add(h); groups[g].add(a)

    for _ in range(n_sims):
        pts = Counter(); gd = Counter(); gf = Counter()
        for home, away, _g in group_fixtures:
            lh, la = ratings_to_lambdas(elo.get(home, 1500), elo.get(away, 1500),
                                        neutral=True)
            hg, ag = rng.poisson(lh), rng.poisson(la)
            gd[home] += hg - ag; gd[away] += ag - hg
            gf[home] += hg; gf[away] += ag
            if hg > ag:   pts[home] += 3
            elif hg < ag: pts[away] += 3
            else:         pts[home] += 1; pts[away] += 1

        key = lambda t: (pts[t], gd[t], gf[t], rng.random())
        winners, runners, thirds = [], [], []
        for g, members in groups.items():
            order = sorted(members, key=key, reverse=True)
            winners.append(order[0]); runners.append(order[1]); thirds.append(order[2])
        best_thirds = sorted(thirds, key=key, reverse=True)[:8]

        # Round of 32: winners seeded against shuffled runners-up + best thirds,
        # avoiding same-group rematches where possible.
        unseeded = runners + best_thirds
        rng.shuffle(winners); rng.shuffle(unseeded)
        team_group = {t: g for g, ms in groups.items() for t in ms}
        pairs = []
        for w in winners:
            j = next((k for k, u in enumerate(unseeded)
                      if team_group[u] != team_group[w]), 0)
            pairs.append((w, unseeded.pop(j)))
        extras = [t for t in unseeded]
        rng.shuffle(extras)
        pairs += [(extras[i], extras[i + 1]) for i in range(0, len(extras), 2)]

        alive = pairs
        while len(alive) >= 1:
            nxt = []
            for a, b in alive:
                p_a = expected_score(elo.get(a, 1500), elo.get(b, 1500))
                nxt.append(a if rng.random() < p_a else b)
            if len(nxt) == 16:
                for t in nxt: last16[t] += 1
            if len(nxt) == 1:
                titles[nxt[0]] += 1
                break
            rng.shuffle(nxt)
            alive = [(nxt[i], nxt[i + 1]) for i in range(0, len(nxt), 2)]

    return titles, last16


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    fixtures, elo = load_inputs()
    print(f"{len(fixtures)} group fixtures, {len(elo)} rated nations, {n} sims\n")
    titles, last16 = simulate(fixtures, elo, n_sims=n)
    print(f"{'team':22s} {'P(champion)':>12s} {'P(last 16)':>11s}")
    for team, wins in titles.most_common(12):
        print(f"{team:22s} {wins / n:12.1%} {last16[team] / n:11.1%}")

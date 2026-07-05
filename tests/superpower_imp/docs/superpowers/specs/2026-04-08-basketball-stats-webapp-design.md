# Basketball Stats Web App — Design Spec

**Date:** 2026-04-08
**Status:** Approved

---

## Overview

A local Flask web app that loads `basketball_stats.csv`, cleans the data, computes three derived player metrics, and displays everything in a dark-themed, sortable HTML table with top/bottom PER highlights.

---

## File Structure

```
superpower_imp/
├── basketball_stats.csv        # source data (existing)
├── app.py                      # Flask app, data pipeline
└── templates/
    └── index.html              # dark dashboard table
```

Start command: `python app.py`
Port: `8083`

---

## Data Layer (`app.py`)

### Loading & Cleaning

1. Load `basketball_stats.csv` with `pandas.read_csv()`
2. Standardize column names: `df.columns = df.columns.str.lower().str.replace(' ', '_')`
3. Drop fully-empty rows: `df.dropna(how='all')`
4. Fill missing numeric values with column mean: `df.fillna(df.select_dtypes(include='number').mean())`

### Source columns (after cleaning)

| Column | Type | Notes |
|---|---|---|
| `player_name` | str | |
| `team` | str | |
| `points` | float | |
| `rebounds` | float | |
| `assists` | float | |
| `turnovers` | float | one missing value → filled with mean |
| `field_goal_pct` | float | |
| `three_point_pct` | float | |
| `free_throw_pct` | float | |

### Derived Metrics

All three are added as new columns after cleaning.

**True Shooting %**
```
true_shooting_pct = points / (2 * (points / field_goal_pct + 0.44 * (points / free_throw_pct)))
```
Approximates TS% without raw shot attempt counts, using the percentage columns available.

**Assist-to-Turnover Ratio**
```
assist_to_turnover_ratio = assists / turnovers
```

**Player Efficiency Rating (PER)**
```
per = (points + rebounds + assists - turnovers) / 30
```
Games approximated as the constant 30.

### Display Rounding

- Source percentage columns (`field_goal_pct`, `three_point_pct`, `free_throw_pct`): displayed as-is (3 decimal places from source)
- Source counting columns (`points`, `rebounds`, `assists`, `turnovers`): displayed as-is (1 decimal place from source)
- `true_shooting_pct`: rounded to 3 decimal places
- `assist_to_turnover_ratio`: rounded to 2 decimal places
- `per`: rounded to 2 decimal places

### Top/Bottom PER classification

After calculating PER, identify:
- `top3`: set of `player_name` values for the 3 highest PER players
- `bottom3`: set of `player_name` values for the 3 lowest PER players

These are passed to the template for row-level highlighting. If a player appears in both (edge case with <6 players), top3 takes precedence.

### Flask route

`GET /` — runs the data pipeline, renders `index.html` with:
- `players`: list of dicts (one per row, all 12 columns)
- `top3`: set of player names
- `bottom3`: set of player names
- `columns`: ordered list of column display names for table headers

---

## Frontend (`templates/index.html`)

### Visual Style — Dark Dashboard

| Element | Value |
|---|---|
| Page background | `#0f172a` |
| Table header background | `#1e293b` |
| Header text | `#94a3b8` |
| Row alternating (odd) | `#1e293b` |
| Row alternating (even) | `#0f172a` |
| Default cell text | `#e2e8f0` |
| Top 3 row left border | `3px solid #22c55e` |
| Top 3 PER cell text | `#4ade80` |
| Top 3 row background | `rgba(34, 197, 94, 0.08)` |
| Bottom 3 row left border | `3px solid #ef4444` |
| Bottom 3 PER cell text | `#f87171` |
| Bottom 3 row background | `rgba(239, 68, 68, 0.08)` |
| Font | `system-ui, sans-serif` |

### Column Order (left to right)

1. `player_name` → Player
2. `team` → Team
3. `points` → PTS
4. `rebounds` → REB
5. `assists` → AST
6. `turnovers` → TOV
7. `field_goal_pct` → FG%
8. `three_point_pct` → 3P%
9. `free_throw_pct` → FT%
10. `true_shooting_pct` → TS%
11. `assist_to_turnover_ratio` → AST/TOV
12. `per` → PER

### Sortable Columns

- All column headers are clickable
- Clicking a header sorts the table by that column (ascending first, then toggle to descending)
- Active sort column header shows a directional arrow indicator (↑ / ↓)
- Sorting is client-side vanilla JS — no server round-trips
- Numeric columns sort numerically; string columns sort lexicographically
- Sort state resets if the page is reloaded

### PER Highlighting Logic (Jinja2)

```jinja
{% if player.player_name in top3 %}
  class="row-top"
{% elif player.player_name in bottom3 %}
  class="row-bottom"
{% endif %}
```

The PER cell additionally gets `.cell-top` or `.cell-bottom` class for colored text.

---

## Error Handling

- If `basketball_stats.csv` is not found, Flask returns a plain 500 with a clear message.
- No other error states are in scope; data is known-good except for the one documented missing value.

---

## Dependencies

```
flask
pandas
```

Install: `pip install flask pandas`

---

## Out of Scope

- Pagination
- Search/filter
- Authentication
- Persistent storage
- Mobile-specific layout
- CSV upload UI

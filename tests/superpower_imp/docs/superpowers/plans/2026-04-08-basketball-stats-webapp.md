# Basketball Stats Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask web app that loads `basketball_stats.csv`, cleans data, computes three player metrics, and displays all columns in a dark-themed sortable HTML table with top/bottom 3 PER rows highlighted.

**Architecture:** A single Flask route in `app.py` runs a pandas data pipeline (clean → compute → classify) and passes the result to `templates/index.html`, which renders a fully client-side sortable table. The data pipeline is split into a testable `process_dataframe` function and a `load_data` wrapper that reads from disk.

**Tech Stack:** Python 3, Flask, pandas, vanilla JS (client-side sort), Jinja2 templates, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Create | Pin flask and pandas |
| `app.py` | Create | Data pipeline + Flask route |
| `templates/index.html` | Create | Dark table, sort JS, PER highlights |
| `tests/test_data.py` | Create | Unit tests for data pipeline functions |

---

### Task 1: Create requirements.txt

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
flask
pandas
pytest
```

Save to `requirements.txt` in the project root.

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: packages install without error.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requirements.txt with flask, pandas, pytest"
```

---

### Task 2: Write failing tests for the data pipeline

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_data.py`

- [ ] **Step 1: Create the tests directory and empty __init__.py**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 2: Write tests/test_data.py**

```python
import math
import pandas as pd
import pytest
from app import process_dataframe, get_top_bottom


def make_df(turnovers=None):
    """Return a minimal 6-player DataFrame with optional missing turnovers."""
    data = {
        'player_name': ['Alice', 'Bob', 'Charlie', 'Dave', 'Eve', 'Frank'],
        'team':        ['A',     'B',   'C',       'D',    'E',   'F'],
        'points':      [20.0,    10.0,  15.0,      25.0,   8.0,   18.0],
        'rebounds':    [5.0,     3.0,   8.0,       7.0,    2.0,   6.0],
        'assists':     [4.0,     2.0,   3.0,       5.0,    1.0,   4.0],
        'turnovers':   [2.0,     1.0,   1.5,       3.0,    0.5,   2.0],
        'field_goal_pct': [0.5,  0.4,   0.45,      0.55,   0.38,  0.48],
        'three_point_pct': [0.4, 0.3,   0.35,      0.32,   0.25,  0.38],
        'free_throw_pct': [0.8,  0.7,   0.75,      0.85,   0.65,  0.78],
    }
    if turnovers is not None:
        data['turnovers'] = turnovers
    return pd.DataFrame(data)


def test_column_names_standardized():
    """process_dataframe normalizes column names to lowercase with underscores."""
    df = make_df()
    df.columns = ['Player Name', 'Team', 'Points', 'Rebounds', 'Assists',
                  'Turnovers', 'Field Goal Pct', 'Three Point Pct', 'Free Throw Pct']
    result = process_dataframe(df)
    assert 'player_name' in result.columns
    assert 'field_goal_pct' in result.columns
    assert 'three_point_pct' in result.columns


def test_empty_rows_dropped():
    """process_dataframe drops fully-empty rows (e.g. trailing blank CSV line)."""
    df = make_df()
    empty_row = pd.DataFrame([[None] * len(df.columns)], columns=df.columns)
    df_with_blank = pd.concat([df, empty_row], ignore_index=True)
    result = process_dataframe(df_with_blank)
    assert len(result) == 6


def test_missing_numeric_filled_with_mean():
    """process_dataframe fills a missing turnovers value with the column mean."""
    turnovers = [2.0, 1.0, 1.5, 3.0, 0.5, None]  # Frank is missing
    df = make_df(turnovers=turnovers)
    result = process_dataframe(df)
    expected_mean = sum([2.0, 1.0, 1.5, 3.0, 0.5]) / 5  # mean of non-null values
    assert not result['turnovers'].isna().any()
    assert math.isclose(result.loc[result['player_name'] == 'Frank', 'turnovers'].iloc[0],
                        expected_mean, rel_tol=1e-5)


def test_true_shooting_pct_calculated():
    """process_dataframe adds true_shooting_pct column with correct values."""
    df = make_df()
    result = process_dataframe(df)
    assert 'true_shooting_pct' in result.columns
    # Manual check for Alice: 20 / (2 * (20/0.5 + 0.44 * (20/0.8))) = 20 / (2 * (40 + 11)) = 20/102 ≈ 0.196
    alice = result.loc[result['player_name'] == 'Alice', 'true_shooting_pct'].iloc[0]
    expected = round(20.0 / (2 * (20.0 / 0.5 + 0.44 * (20.0 / 0.8))), 3)
    assert math.isclose(alice, expected, rel_tol=1e-4)


def test_assist_to_turnover_ratio_calculated():
    """process_dataframe adds assist_to_turnover_ratio column with correct values."""
    df = make_df()
    result = process_dataframe(df)
    assert 'assist_to_turnover_ratio' in result.columns
    # Alice: 4 / 2 = 2.0
    alice = result.loc[result['player_name'] == 'Alice', 'assist_to_turnover_ratio'].iloc[0]
    assert math.isclose(alice, 2.0, rel_tol=1e-5)


def test_per_calculated():
    """process_dataframe adds per column with correct values."""
    df = make_df()
    result = process_dataframe(df)
    assert 'per' in result.columns
    # Alice: (20 + 5 + 4 - 2) / 30 = 27/30 = 0.9
    alice = result.loc[result['player_name'] == 'Alice', 'per'].iloc[0]
    assert math.isclose(alice, round(27.0 / 30, 2), rel_tol=1e-5)


def test_per_rounded_to_2_decimal_places():
    """PER values are rounded to 2 decimal places."""
    df = make_df()
    result = process_dataframe(df)
    for val in result['per']:
        assert val == round(val, 2)


def test_assist_to_turnover_rounded_to_2_decimal_places():
    """assist_to_turnover_ratio values are rounded to 2 decimal places."""
    df = make_df()
    result = process_dataframe(df)
    for val in result['assist_to_turnover_ratio']:
        assert val == round(val, 2)


def test_true_shooting_pct_rounded_to_3_decimal_places():
    """true_shooting_pct values are rounded to 3 decimal places."""
    df = make_df()
    result = process_dataframe(df)
    for val in result['true_shooting_pct']:
        assert val == round(val, 3)


def test_get_top_bottom_returns_correct_sets():
    """get_top_bottom returns sets of the 3 highest and 3 lowest PER player names."""
    df = make_df()
    df = process_dataframe(df)
    top3, bottom3 = get_top_bottom(df)
    # PER = (pts + reb + ast - tov) / 30
    # Alice:   (20+5+4-2)/30  = 0.90
    # Bob:     (10+3+2-1)/30  = 0.47
    # Charlie: (15+8+3-1.5)/30= 0.82
    # Dave:    (25+7+5-3)/30  = 1.13  <- top
    # Eve:     (8+2+1-0.5)/30 = 0.35  <- bottom
    # Frank:   (18+6+4-2)/30  = 0.87
    # Top 3 by PER: Dave(1.13), Alice(0.90), Frank(0.87)
    # Bottom 3 by PER: Eve(0.35), Bob(0.47), Charlie(0.82)
    assert top3 == {'Dave', 'Alice', 'Frank'}
    assert bottom3 == {'Eve', 'Bob', 'Charlie'}
    # No overlap
    assert top3.isdisjoint(bottom3)


def test_get_top_bottom_top3_takes_precedence():
    """If fewer than 6 players, top3 names are excluded from bottom3."""
    # Build 4-player DataFrame where top/bottom would overlap
    data = {
        'player_name': ['P1', 'P2', 'P3', 'P4'],
        'team': ['A', 'B', 'C', 'D'],
        'points': [30.0, 20.0, 10.0, 5.0],
        'rebounds': [5.0, 5.0, 5.0, 5.0],
        'assists': [5.0, 5.0, 5.0, 5.0],
        'turnovers': [1.0, 1.0, 1.0, 1.0],
        'field_goal_pct': [0.5, 0.5, 0.5, 0.5],
        'three_point_pct': [0.35, 0.35, 0.35, 0.35],
        'free_throw_pct': [0.75, 0.75, 0.75, 0.75],
        'true_shooting_pct': [0.5, 0.5, 0.5, 0.5],
        'assist_to_turnover_ratio': [5.0, 5.0, 5.0, 5.0],
        'per': [1.3, 0.97, 0.63, 0.47],
    }
    df = pd.DataFrame(data)
    top3, bottom3 = get_top_bottom(df)
    assert top3.isdisjoint(bottom3)
```

- [ ] **Step 3: Run tests to verify they all fail (functions not yet defined)**

```bash
cd /Users/neilmahajan/Desktop/Python/tests/superpower_imp
pytest tests/test_data.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'process_dataframe' from 'app'` (or similar — app.py doesn't exist yet).

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/__init__.py tests/test_data.py
git commit -m "test: add failing data pipeline tests"
```

---

### Task 3: Implement the data pipeline in app.py

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create app.py with process_dataframe and get_top_bottom**

```python
import pandas as pd
from flask import Flask, render_template

app = Flask(__name__)

COLUMN_LABELS = {
    'player_name':            'Player',
    'team':                   'Team',
    'points':                 'PTS',
    'rebounds':               'REB',
    'assists':                'AST',
    'turnovers':              'TOV',
    'field_goal_pct':         'FG%',
    'three_point_pct':        '3P%',
    'free_throw_pct':         'FT%',
    'true_shooting_pct':      'TS%',
    'assist_to_turnover_ratio': 'AST/TOV',
    'per':                    'PER',
}

COLUMN_ORDER = list(COLUMN_LABELS.keys())


def process_dataframe(df):
    """Clean raw DataFrame and compute derived metrics."""
    df = df.copy()
    df.columns = df.columns.str.lower().str.replace(' ', '_')
    df = df.dropna(how='all')
    df = df.fillna(df.select_dtypes(include='number').mean())

    df['true_shooting_pct'] = (
        df['points'] / (2 * (df['points'] / df['field_goal_pct']
                             + 0.44 * (df['points'] / df['free_throw_pct'])))
    ).round(3)

    df['assist_to_turnover_ratio'] = (df['assists'] / df['turnovers']).round(2)

    df['per'] = (
        (df['points'] + df['rebounds'] + df['assists'] - df['turnovers']) / 30
    ).round(2)

    return df


def get_top_bottom(df, n=3):
    """Return (top_n, bottom_n) sets of player_name by PER. top_n takes precedence."""
    top3 = set(df.nlargest(n, 'per')['player_name'])
    bottom3 = set(df.nsmallest(n, 'per')['player_name']) - top3
    return top3, bottom3


def load_data(csv_path='basketball_stats.csv'):
    df = pd.read_csv(csv_path)
    return process_dataframe(df)


@app.route('/')
def index():
    try:
        df = load_data()
    except FileNotFoundError:
        return 'Error: basketball_stats.csv not found in the application directory.', 500

    top3, bottom3 = get_top_bottom(df)
    players = df[COLUMN_ORDER].to_dict(orient='records')
    columns = list(COLUMN_LABELS.items())

    return render_template(
        'index.html',
        players=players,
        top3=top3,
        bottom3=bottom3,
        columns=columns,
    )


if __name__ == '__main__':
    app.run(debug=True, port=8083)
```

- [ ] **Step 2: Run tests and verify they all pass**

```bash
cd /Users/neilmahajan/Desktop/Python/tests/superpower_imp
pytest tests/test_data.py -v
```

Expected output (all 11 tests pass):
```
tests/test_data.py::test_column_names_standardized PASSED
tests/test_data.py::test_empty_rows_dropped PASSED
tests/test_data.py::test_missing_numeric_filled_with_mean PASSED
tests/test_data.py::test_true_shooting_pct_calculated PASSED
tests/test_data.py::test_assist_to_turnover_ratio_calculated PASSED
tests/test_data.py::test_per_calculated PASSED
tests/test_data.py::test_per_rounded_to_2_decimal_places PASSED
tests/test_data.py::test_assist_to_turnover_rounded_to_2_decimal_places PASSED
tests/test_data.py::test_true_shooting_pct_rounded_to_3_decimal_places PASSED
tests/test_data.py::test_get_top_bottom_returns_correct_sets PASSED
tests/test_data.py::test_get_top_bottom_top3_takes_precedence PASSED
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: implement data pipeline with process_dataframe and get_top_bottom"
```

---

### Task 4: Build templates/index.html

**Files:**
- Create: `templates/index.html`

- [ ] **Step 1: Create the templates directory and index.html**

Create `templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Basketball Stats Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #0f172a;
      color: #e2e8f0;
      font-family: system-ui, sans-serif;
      padding: 2rem;
    }

    h1 {
      font-size: 1.5rem;
      font-weight: 700;
      color: #f1f5f9;
      margin-bottom: 1.5rem;
    }

    .table-wrapper {
      overflow-x: auto;
      border-radius: 8px;
      border: 1px solid #1e293b;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    thead tr {
      background: #1e293b;
    }

    th {
      padding: 10px 14px;
      text-align: right;
      color: #94a3b8;
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      cursor: pointer;
      white-space: nowrap;
      user-select: none;
      border-bottom: 1px solid #334155;
    }

    th:first-child, th:nth-child(2) { text-align: left; }
    th:hover { color: #e2e8f0; }

    th .arrow { margin-left: 4px; opacity: 0.35; font-style: normal; }
    th.sort-asc  .arrow::after { content: '↑'; opacity: 1; }
    th.sort-desc .arrow::after { content: '↓'; opacity: 1; }
    th:not(.sort-asc):not(.sort-desc) .arrow::after { content: '↕'; }

    tbody tr:nth-child(odd)  { background: #1e293b; }
    tbody tr:nth-child(even) { background: #0f172a; }
    tbody tr:hover           { background: #263348; }

    td {
      padding: 9px 14px;
      text-align: right;
      color: #e2e8f0;
      border-bottom: 1px solid #1e293b;
    }

    td:first-child, td:nth-child(2) { text-align: left; }
    td:first-child { font-weight: 600; }

    /* Top 3 PER */
    tr.row-top {
      background: rgba(34, 197, 94, 0.08) !important;
      border-left: 3px solid #22c55e;
    }
    tr.row-top td:first-child { color: #4ade80; }
    td.cell-top  { color: #4ade80; font-weight: 700; }

    /* Bottom 3 PER */
    tr.row-bottom {
      background: rgba(239, 68, 68, 0.08) !important;
      border-left: 3px solid #ef4444;
    }
    tr.row-bottom td:first-child { color: #f87171; }
    td.cell-bottom { color: #f87171; font-weight: 700; }

    .legend {
      margin-top: 1rem;
      font-size: 0.75rem;
      color: #64748b;
      display: flex;
      gap: 1.5rem;
    }

    .dot {
      width: 8px; height: 8px; border-radius: 50%;
      display: inline-block; margin-right: 5px;
      vertical-align: middle;
    }
  </style>
</head>
<body>
  <h1>Basketball Stats Dashboard</h1>

  <div class="table-wrapper">
    <table id="stats-table">
      <thead>
        <tr>
          {% for col_key, col_label in columns %}
          <th onclick="sortTable('{{ col_key }}')" data-col="{{ col_key }}">
            {{ col_label }}<span class="arrow"></span>
          </th>
          {% endfor %}
        </tr>
      </thead>
      <tbody id="table-body">
        {% for player in players %}
        <tr {% if player.player_name in top3 %}class="row-top"
            {% elif player.player_name in bottom3 %}class="row-bottom"{% endif %}>
          {% for col_key, col_label in columns %}
          <td{% if col_key == 'per' %} {% if player.player_name in top3 %}class="cell-top"{% elif player.player_name in bottom3 %}class="cell-bottom"{% endif %}{% endif %}>
            {{ player[col_key] }}
          </td>
          {% endfor %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="legend">
    <span><span class="dot" style="background:#22c55e"></span>Top 3 PER</span>
    <span><span class="dot" style="background:#ef4444"></span>Bottom 3 PER</span>
  </div>

  <script>
    const COLUMNS = {{ columns | tojson }};
    let sortState = { col: null, asc: true };

    function sortTable(colKey) {
      const tbody = document.getElementById('table-body');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const colIndex = COLUMNS.findIndex(([k]) => k === colKey);

      sortState.asc = sortState.col === colKey ? !sortState.asc : true;
      sortState.col = colKey;

      const stringCols = new Set(['player_name', 'team']);

      rows.sort((a, b) => {
        const aVal = a.cells[colIndex].textContent.trim();
        const bVal = b.cells[colIndex].textContent.trim();
        const cmp = stringCols.has(colKey)
          ? aVal.localeCompare(bVal)
          : parseFloat(aVal) - parseFloat(bVal);
        return sortState.asc ? cmp : -cmp;
      });

      rows.forEach(r => tbody.appendChild(r));

      document.querySelectorAll('th').forEach((th, i) => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (COLUMNS[i][0] === colKey) {
          th.classList.add(sortState.asc ? 'sort-asc' : 'sort-desc');
        }
      });
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Start the app and verify it runs**

```bash
cd /Users/neilmahajan/Desktop/Python/tests/superpower_imp
python app.py
```

Expected: Flask starts on `http://localhost:8083`

- [ ] **Step 3: Open http://localhost:8083 and verify**

Checklist:
- [ ] Table displays all 20 players
- [ ] All 12 columns visible (Player, Team, PTS, REB, AST, TOV, FG%, 3P%, FT%, TS%, AST/TOV, PER)
- [ ] Top 3 PER rows have green left border and green player name text; PER cell is green bold
- [ ] Bottom 3 PER rows have red left border and red player name text; PER cell is red bold
- [ ] Clicking any column header sorts the table; arrow indicator updates
- [ ] Clicking the same header again reverses sort order
- [ ] Legend shows green/red dots with labels at the bottom

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: add dark dashboard table template with sortable columns and PER highlights"
```

---

### Task 5: Final verification and cleanup

**Files:**
- No new files

- [ ] **Step 1: Run the full test suite one final time**

```bash
cd /Users/neilmahajan/Desktop/Python/tests/superpower_imp
pytest tests/test_data.py -v
```

Expected: all 11 tests pass, 0 failures.

- [ ] **Step 2: Verify the FileNotFoundError handler**

In a separate terminal, temporarily rename the CSV and hit the route:

```bash
mv basketball_stats.csv basketball_stats.csv.bak
curl -s http://localhost:8083/
# Expected: "Error: basketball_stats.csv not found in the application directory."
mv basketball_stats.csv.bak basketball_stats.csv
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git status  # confirm only expected files are staged
git commit -m "chore: final cleanup and verification"
```

import pandas as pd
from flask import Flask, render_template_string

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Basketball Stats</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .table-wrapper { overflow-x: auto; }
        table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th { background: #2c3e50; color: white; padding: 10px 12px; text-align: left; font-size: 13px; }
        td { padding: 9px 12px; border-bottom: 1px solid #ddd; font-size: 13px; }
        tr:hover { filter: brightness(0.96); }
        .top { background: #c8f7c5; }
        .bottom { background: #f7c5c5; }
        .legend { margin: 16px 0; display: flex; gap: 20px; flex-wrap: wrap; }
        .legend-item { display: flex; align-items: center; gap: 8px; font-size: 13px; }
        .swatch { width: 18px; height: 18px; border-radius: 3px; }
        @media (max-width: 600px) {
          body { padding: 12px 8px; }
          th, td { padding: 6px 8px; font-size: 11px; }
        }
    </style>
</head>
<body>
    <h1>Basketball Stats</h1>
    <div class="legend">
        <div class="legend-item"><div class="swatch" style="background:#c8f7c5"></div>Top 3 PER</div>
        <div class="legend-item"><div class="swatch" style="background:#f7c5c5"></div>Bottom 3 PER</div>
    </div>
    <div class="table-wrapper">
    <table>
        <thead>
            <tr>{% for col in columns %}<th>{{ col }}</th>{% endfor %}</tr>
        </thead>
        <tbody>
            {% for row in rows %}
            <tr class="{{ row.css }}">
                {% for val in row.values %}<td>{{ val }}</td>{% endfor %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</body>
</html>
"""

def load_and_process():
    df = pd.read_csv("basketball_stats.csv")

    # Standardize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Fill missing values with column averages
    df = df.fillna(df.select_dtypes(include="number").mean())

    # Calculate metrics
    df["true_shooting_pct"] = df["points"] / (
        2 * (df["points"] / df["field_goal_pct"] + 0.44 * (df["points"] / df["free_throw_pct"]))
    )
    df["assist_to_turnover_ratio"] = df["assists"] / df["turnovers"]
    df["player_efficiency_rating"] = (
        df["points"] + df["rebounds"] + df["assists"] - df["turnovers"]
    ) / 30

    return df

@app.route("/")
def index():
    df = load_and_process()

    per_sorted = df["player_efficiency_rating"].sort_values()
    bottom3 = set(per_sorted.head(3).index)
    top3 = set(per_sorted.tail(3).index)

    display_cols = [
        "player_name", "team", "points", "rebounds", "assists", "turnovers",
        "field_goal_pct", "three_point_pct", "free_throw_pct",
        "true_shooting_pct", "assist_to_turnover_ratio", "player_efficiency_rating"
    ]
    headers = [c.replace("_", " ").title() for c in display_cols]

    rows = []
    for idx, row in df.iterrows():
        css = "top" if idx in top3 else ("bottom" if idx in bottom3 else "")
        vals = []
        for col in display_cols:
            v = row[col]
            vals.append(f"{v:.3f}" if isinstance(v, float) else v)
        rows.append({"css": css, "values": vals})

    return render_template_string(HTML, columns=headers, rows=rows)

if __name__ == "__main__":
    app.run(port=8084, debug=True)

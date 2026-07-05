import pandas as pd
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Basketball Stats</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        h1 { text-align: center; }
        table { border-collapse: collapse; width: 100%; background: #fff; }
        th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: center; }
        th { background: #333; color: #fff; position: sticky; top: 0; }
        tr:nth-child(even) { background: #f9f9f9; }
        tr.top { background: #c6efce; }
        tr.bottom { background: #ffc7ce; }
        .table-wrapper { overflow-x: auto; }
        @media (max-width: 600px) {
          body { margin: 16px 8px; }
          h1 { font-size: 1.2rem; }
          th, td { padding: 6px 6px; font-size: 0.75rem; }
        }
    </style>
</head>
<body>
    <h1>Basketball Player Stats</h1>
    <div class="table-wrapper">
    <table>
        <tr>
            {% for col in columns %}
            <th>{{ col }}</th>
            {% endfor %}
        </tr>
        {% for row in rows %}
        <tr class="{{ row.row_class }}">
            {% for col in columns %}
            <td>{{ row[col] }}</td>
            {% endfor %}
        </tr>
        {% endfor %}
    </table>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    df = pd.read_csv("basketball_stats.csv")

    # Standardize column names
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Fill missing numeric values with column averages
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())

    # Calculated metrics
    df["true_shooting_pct"] = (
        df["points"]
        / (2 * (df["points"] / df["field_goal_pct"] + 0.44 * (df["points"] / df["free_throw_pct"])))
    ).round(4)

    df["ast_to_tov"] = (df["assists"] / df["turnovers"]).round(2)

    games = 30
    df["per"] = ((df["points"] + df["rebounds"] + df["assists"] - df["turnovers"]) / games).round(2)

    # Determine top/bottom 3 by PER
    sorted_per = df["per"].sort_values()
    bottom3 = sorted_per.head(3).index
    top3 = sorted_per.tail(3).index

    # Round all numeric columns for display
    for c in df.select_dtypes(include="number").columns:
        df[c] = df[c].round(3)

    rows = []
    for idx, row in df.iterrows():
        r = row.to_dict()
        if idx in top3:
            r["row_class"] = "top"
        elif idx in bottom3:
            r["row_class"] = "bottom"
        else:
            r["row_class"] = ""
        rows.append(r)

    return render_template_string(HTML_TEMPLATE, columns=df.columns.tolist(), rows=rows)


if __name__ == "__main__":
    app.run(debug=True, port=8082)

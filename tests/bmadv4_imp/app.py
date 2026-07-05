from pathlib import Path
import pandas as pd
from flask import Flask, render_template

app = Flask(__name__)

CSV_PATH = Path(__file__).parent / "basketball_stats.csv"
GAMES = 30
PORT = 8080

CALC_COLS = ["true_shooting_pct", "ast_to_ratio", "per"]

COLUMN_LABELS = {
    "player_name": "Player",
    "team": "Team",
    "points": "PTS",
    "rebounds": "REB",
    "assists": "AST",
    "turnovers": "TO",
    "field_goal_pct": "FG%",
    "three_point_pct": "3P%",
    "free_throw_pct": "FT%",
    "true_shooting_pct": "TS%",
    "ast_to_ratio": "AST/TO",
    "per": "PER",
}


def load_and_process():
    df = pd.read_csv(CSV_PATH)

    # Standardize column names to lowercase with underscores
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_", regex=False)

    # Fill missing numeric values with column mean
    num_cols = df.select_dtypes(include="number").columns
    df[num_cols] = df[num_cols].fillna(df[num_cols].mean())

    # True Shooting % — approximated as per spec:
    # TS% = points / (2 * (points/fg_pct + 0.44 * points/ft_pct))
    df["true_shooting_pct"] = df["points"] / (
        2 * (df["points"] / df["field_goal_pct"] + 0.44 * df["points"] / df["free_throw_pct"])
    )

    # Assist-to-Turnover Ratio
    df["ast_to_ratio"] = df["assists"] / df["turnovers"]

    # Player Efficiency Rating (games approximated as constant 30)
    df["per"] = (df["points"] + df["rebounds"] + df["assists"] - df["turnovers"]) / GAMES

    # Round all numeric columns in a single pass
    all_num_cols = num_cols.tolist() + CALC_COLS
    df[all_num_cols] = df[all_num_cols].round(3)

    df = df.sort_values("per", ascending=False).reset_index(drop=True)

    top3 = set(df.head(3)["player_name"])
    bot3 = set(df.tail(3)["player_name"])

    return df, top3, bot3


@app.route("/")
def index():
    df, top3, bot3 = load_and_process()
    return render_template(
        "index.html",
        columns=list(df.columns),
        rows=df.to_dict(orient="records"),
        top3=top3,
        bot3=bot3,
        col_labels=COLUMN_LABELS,
        calc_cols=set(CALC_COLS),
    )


if __name__ == "__main__":
    app.run(debug=True, port=PORT)

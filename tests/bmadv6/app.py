from flask import Flask, render_template
import pandas as pd
import os

app = Flask(__name__)

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'basketball_stats.csv')

@app.route('/')
def index():
    df = pd.read_csv(CSV_PATH)

    # Standardize column names
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    # Fill missing numeric values with column mean (rounded to 2dp to avoid float noise)
    for col in df.select_dtypes(include='number').columns:
        df[col] = df[col].fillna(round(df[col].mean(), 2))

    eps = 1e-9

    # True Shooting % approximation: TS% = pts / (2*FGA + 0.44*FTA)
    # where FGA ≈ pts/fgp and FTA ≈ pts/ftp
    # = 1 / (2/fgp + 0.44/ftp)
    df['true_shooting_pct'] = (
        df['points'] / (2 * df['points'] / (df['field_goal_pct'] + eps) + 0.44 * df['points'] / (df['free_throw_pct'] + eps))
    ).round(4)

    # Assist-to-Turnover Ratio
    df['assist_to_turnover_ratio'] = (
        df['assists'] / df['turnovers'].replace(0, float('nan'))
    ).round(4)

    # Player Efficiency Rating (games = 30)
    GAMES = 30
    df['player_efficiency_rating'] = (
        (df['points'] + df['rebounds'] + df['assists'] - df['turnovers']) / GAMES
    ).round(4)

    # Sort by PER descending
    df = df.sort_values('player_efficiency_rating', ascending=False).reset_index(drop=True)

    # Identify top 3 / bottom 3 by PER
    per = df['player_efficiency_rating']
    top3 = set(per.nlargest(3).index)
    bottom3 = set(per.nsmallest(3).index)

    rows = []
    for i, row in df.iterrows():
        if i in top3:
            css = 'top'
        elif i in bottom3:
            css = 'bottom'
        else:
            css = ''
        rows.append((css, row.to_dict()))

    columns = df.columns.tolist()
    return render_template('index.html', columns=columns, rows=rows)


if __name__ == '__main__':
    app.run(port=8085, debug=True)

import os
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
    num_cols = df.select_dtypes(include='number').columns
    df[num_cols] = df[num_cols].fillna(df[num_cols].mean())
    counting_cols = ['points', 'rebounds', 'assists', 'turnovers']
    df[counting_cols] = df[counting_cols].round(1)

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


_DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'basketball_stats.csv')


def load_data(csv_path=_DEFAULT_CSV):
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

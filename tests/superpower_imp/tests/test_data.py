import math
import pandas as pd
import pytest
from tests.bmadv6.app import process_dataframe, get_top_bottom


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

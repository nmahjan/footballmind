# Basketball Stats Web App

## Goal
Build a simple Flask web app that loads basketball_stats.csv, cleans the data, calculates three metrics, and displays everything in a color-coded HTML table.

## Requirements
1. Load basketball_stats.csv from the project folder
2. Clean the data — fill missing values with column average, standardize column names to lowercase with underscores
3. Calculate three new metrics:
   - True Shooting %: points / (2 * (points / field_goal_pct + 0.44 * (points / free_throw_pct)))
   - Assist-to-Turnover Ratio: assists / turnovers
   - Player Efficiency Rating: (points + rebounds + assists - turnovers) / 30
4. Display all original and calculated columns in a clean HTML table
5. Highlight top 3 players by PER in green, bottom 3 in red
6. Use Python and Flask for the backend, plain HTML and CSS for the frontend
7. Run on port 8084
8. Start with: python app.py

## Done When
- App runs on http://127.0.0.1:8084
- All 20 players display in the table
- Top 3 PER highlighted green, bottom 3 red
- Missing turnover value for Samson Adeyemi is filled with column average

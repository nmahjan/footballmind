# Ralph Agent Configuration

## Build Instructions

```bash
# No build step required — pure Python
echo 'No build step needed'
```

## Test Instructions

```bash
# Run tests
python -m pytest test_basketball_stats.py -v
```

## Run Instructions

```bash
# Print summary report
python basketball_stats.py
```

## Notes
- Python 3.10+ required (uses built-in `list[dict]` type hints)
- No external dependencies — uses only stdlib (csv, os, typing)
- Main data file: basketball_stats.csv (20 players, 9 stats columns)
- One missing value: Samson Adeyemi has no turnovers value — handled as None

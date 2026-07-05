# Basketball Stats — traycer_imp

A Flask web app that loads `basketball_stats.csv`, computes derived metrics, and displays a sortable stats table with top-3/bottom-3 PER row highlighting.

## Quick start

Run all commands from the `tests/traycer_imp/` directory.

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:8081 in your browser.

## Details

- **Port:** 8081
- **Debug mode:** enabled (auto-reloads on code changes)
- **Data file:** `basketball_stats.csv` is read relative to `app.py`, so the app must be run from `tests/traycer_imp/` or via an absolute path to that directory.

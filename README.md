# FootballMind Repository

This repository contains the FootballMind app in [`footballmind/`](footballmind/).

Repo-level files stay at the root because hosting and automation discover them there:

- `.github/workflows/` runs CI, scheduled sync jobs, and GitHub Pages deploys.
- `render.yaml` configures the Render web service and points into `footballmind/`.
- `.gitignore` applies to the whole repository.

For app architecture, local setup, data jobs, and deployment details, read [`footballmind/README.md`](footballmind/README.md).

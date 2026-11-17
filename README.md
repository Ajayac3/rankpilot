# RankPilot

A search-analytics platform in Python. Collectors pull search, traffic and competitor data into a SQLite warehouse; analysis modules turn it into keyword, content-gap and AI-search reports; a report builder sends a weekly summary.

## Layout
- `collectors/`: 19 data collectors (Search Console, Analytics, Bing, page speed, SERP, backlinks, AI-answer tracking and others)
- `analysis/`: 19 analysis modules (intent classification, keyword difficulty, content gap, share of voice and others)
- `report/`, `alerts/`, `dashboard/`: reporting, alerting and a dashboard
- `compliance/`: rule sets that block prohibited advertising claims
- `profiles/`: one folder per site. `example-legal` and `example-dental` are fictional sample sites.

## Run
```
pip install -e .
python tests/test_profile.py
python run.py --help
```
API keys are read from environment variables; none are stored in this repository.

This is a cleaned public snapshot of a private working repository. All site data in it is fictional.

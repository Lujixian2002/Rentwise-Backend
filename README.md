# RentWise Backend

- Serves community data through REST APIs
- Fetches external signals with a cache-first refresh flow
- Stores and returns:
  - `community_metrics`
  - `dimension_score`
  - `community_comparison`
- Supports community review ingestion and read APIs

## Current API

- `GET /` - service status
- `GET /health` - health check
- `GET /communities/{community_id}` - community profile + metrics
- `GET /communities/{community_id}/reviews` - community reviews
- `POST /compare` - compare two communities

Example:

```bash
curl http://127.0.0.1:8000/health
```

```bash
curl http://127.0.0.1:8000/communities/irvine-spectrum
```

```bash
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "community_a_id": "irvine-spectrum",
    "community_b_id": "woodbridge",
    "weights": {
      "Safety": 1.2,
      "Transit": 1.5
    }
  }'
```

## Quick Start

Run from the project root.

```bash
python -m pip install -r requirements.txt
python -m scripts.fetch_irvine_sample
uvicorn app.main:app --reload
```

## Configuration

Set values in `.env` (optional fields can stay empty):

- `DATABASE_URL` (default is local SQLite if not set)
- `APP_ENV`
- `METRICS_TTL_HOURS`
- `GOOGLE_MAPS_API_KEY`
- `OPENROUTESERVICE_API_KEY`
- `CRIMEOMETER_API_KEY`
- `YELP_API_KEY`
- `YOUTUBE_API_KEY`
- `NASA_EARTHDATA_TOKEN`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`

## Useful Scripts

- `python -m scripts.seed_communities` - seed base community records
- `python -m scripts.fetch_irvine_sample` - create tables, seed, fetch sample metrics
- `python -m scripts.export_share_sql --output sql/2_insert_statements.sql` - export shareable SQL

## Project Structure

```text
app/
  api/           # route handlers
  services/      # ingest, scoring, compare, fetchers
  db/            # models, session, CRUD
  schemas/       # request/response models
  core/          # config and logging
scripts/         # seed/fetch helpers
sql/             # shared SQL files
```

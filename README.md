# RentWise Backend

FastAPI service that powers the RentWise neighborhood comparison tool.

- Serves community profiles, metrics, and side-by-side comparisons through REST APIs
- Fetches external signals (crime, commute, noise, grocery density, nightlights, rent) with a cache-first refresh flow
- Ingests YouTube comments and Google Maps reviews for each community
- Exposes an OpenAI-powered chat endpoint that extracts user preference weights from a natural-language conversation

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/communities` | List all cached communities + metrics |
| `GET` | `/` | Service status |
| `GET` | `/health` | Health check |
| `GET` | `/communities/{community_id}` | Community profile + cached metrics |
| `GET` | `/communities/{community_id}/reviews` | YouTube + Google Maps reviews |
| `POST` | `/communities/{community_id}/insight` | LLM-generated 5-dimension commentary + optional web-grounded community info |
| `POST` | `/compare` | Compare two communities with rule-based scoring plus LLM-generated summary/tradeoffs |
| `POST` | `/chat` | LLM chat that extracts preference weights |
| `POST` | `/recommend` | Rank communities using LLM-derived preference weights |

Examples:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/communities
curl http://127.0.0.1:8000/communities/irvine-spectrum
```

```bash
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "community_a_id": "irvine-spectrum",
    "community_b_id": "woodbridge",
    "weights": { "Safety": 1.2, "Transit": 1.5 }
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I care about safety and parking"}]}'
```

```bash
curl -X POST http://127.0.0.1:8000/communities/woodbridge/insight \
  -H "Content-Type: application/json" \
  -d '{
    "max_reviews": 20,
    "include_web_info": true
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "weights": {
      "safety": 35,
      "transit": 20,
      "convenience": 15,
      "parking": 20,
      "environment": 10
    },
    "top_k": 3
  }'
```

Interactive docs: `http://127.0.0.1:8000/docs`

## Quick Start

```bash
pip install -r requirements.txt
python -m scripts.fetch_irvine_sample   # creates tables, seeds, fetches sample metrics
uvicorn app.main:app --reload --port 8000
```

Database is configured through `DATABASE_URL` in `.env` (or `.env.local`, which takes precedence and is gitignored — use it for personal API keys).

> **Note**: `fetch_irvine_sample` calls live external APIs (OSM Overpass, Google Maps, YouTube, ZORI CSV, VIIRS raster) and takes ~5–10 minutes. It also needs assets in `data/` (Zillow ZORI CSV, VIIRS night-lights tile) and the corresponding API keys to fully populate metrics. If you just want to spin up the project against the same dataset the maintainer is using, use the SQL dump path below instead.

## Reproducing the seeded dataset (fast path)

The `sql/` folder ships pre-exported snapshots so collaborators can boot a working DB in seconds without running any fetchers:

| File | Contents |
|---|---|
| `sql/1_create_tables.sql` | Schema (7 tables) |
| `sql/2_insert_statements.sql` | Data — 27 communities, metrics, dimension scores, review posts |

Steps:

```bash
# 1. Start a Postgres container that matches the expected DATABASE_URL
docker run -d --name rentwise-postgres \
  -e POSTGRES_DB=rentwise \
  -e POSTGRES_USER=rentwise_user \
  -e POSTGRES_PASSWORD=ddbswdjx \
  -p 5432:5432 \
  postgres:16

# 2. Import schema then data (chained on stdin so it's one command)
cat sql/1_create_tables.sql sql/2_insert_statements.sql | \
  docker exec -i -e PGPASSWORD=ddbswdjx rentwise-postgres \
  psql -U rentwise_user -d rentwise

# 3. Verify
docker exec -e PGPASSWORD=ddbswdjx rentwise-postgres \
  psql -U rentwise_user -d rentwise -c "SELECT COUNT(*) FROM community;"
# → expect 27

# 4. Boot the backend against the imported DB
echo 'DATABASE_URL=postgresql://rentwise_user:ddbswdjx@localhost:5432/rentwise' >> .env.local
uvicorn app.main:app --reload --port 8000
```

To regenerate `sql/2_insert_statements.sql` after running fetchers locally:

```bash
PYTHONPATH=. python sql/export_share_sql.py
```

## Configuration

Create a `.env` file in this directory. `DATABASE_URL` is required. The remaining keys are optional — missing keys cause the corresponding fetcher to return `None` gracefully.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Required SQLAlchemy URL for the application database |
| `APP_ENV` | Environment label |
| `METRICS_TTL_HOURS` | Cache TTL for community metrics |
| `OPENAI_API_KEY` | Enables LLM-powered endpoints including `/chat`, `/compare`, and `/communities/{community_id}/insight` |
| `OPENAI_WEB_SEARCH_MODEL` | Optional model override for the web-search portion of `/communities/{community_id}/insight` |
| `OPENAI_WEB_SEARCH_TIMEOUT_SEC` | Timeout for the web-search portion of `/communities/{community_id}/insight` |
| `GOOGLE_MAPS_API_KEY` | Commute times + place reviews |
| `OPENROUTESERVICE_API_KEY` | Commute fallback |
| `YOUTUBE_API_KEY` | YouTube comment ingestion |
| `CRIMEOMETER_API_KEY` | Crime rate (per-100k) |
| `NASA_EARTHDATA_TOKEN` | VIIRS night-activity index |
| `YELP_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `SOCRATA_APP_TOKEN` | Reserved for future fetchers |

## Scripts

- `python -m scripts.seed_communities` — seed base community records
- `python -m scripts.fetch_irvine_sample` — create tables, seed communities, then fetch sample metrics

## Project Structure

```text
app/
  api/routes/      # health, communities, compare, chat
  services/        # ingest, scoring, compare, community_resolver, chat_service
  services/fetchers/   # google_maps, google_maps_reviews, youtube, irvine_crime,
                       # nasa_viirs, openrouteservice, overpass_osm, zillow_zori, geocoding
  db/              # SQLAlchemy models, session, CRUD
  schemas/         # Pydantic request/response models
  core/            # config, logging
  utils/           # small helpers
scripts/           # seed/fetch helpers
sql/               # shared SQL files
data/              # local raster / CSV assets (gitignored)
```

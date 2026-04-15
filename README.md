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
| `POST` | `/communities/{community_id}/insight` | LLM-generated 5-dimension commentary + tradeoff |
| `POST` | `/compare` | Compare two communities (optionally with custom weights) |
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
    "max_reviews": 20
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

Database defaults to local SQLite (`rentwise.db`). To use Postgres, set `DATABASE_URL` in `.env`. The project root ships a `start.sh` that boots a `my-postgres` Docker container along with the backend and frontend.

## Configuration

Create a `.env` file in this directory. All keys except `DATABASE_URL` are optional — missing keys cause the corresponding fetcher to return `None` gracefully.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL; defaults to `sqlite:///./rentwise.db` |
| `APP_ENV` | Environment label |
| `METRICS_TTL_HOURS` | Cache TTL for community metrics |
| `OPENAI_API_KEY` | Enables `POST /chat` (gpt-4o-mini) |
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

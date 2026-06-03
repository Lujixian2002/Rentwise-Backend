# RentWise Backend

RentWise Backend is the FastAPI service for the RentWise neighborhood comparison tool. It provides community profiles, cached neighborhood metrics, renter preference recommendations, side-by-side comparisons, review data, and AI-assisted community reports for Irvine, CA rental communities.

Combined repository: https://github.com/Lujixian2002/Rentwise.git

Live frontend deployment: https://rentwise-cod.pages.dev/

Demo video: https://drive.google.com/file/d/1BufoYp1h5vMAkXCaezZZxoiZ-KXkTJWT/view?usp=sharing

## Team Members

| Name | Github |
| --- | --- |
| Kefei Wu | wukef2425 |
| Jason Wu | CyberObservers |
| Haofeng Li | noelistheone |
| Jixian Lu | Lujixian2002 |

## Features Implemented

- REST APIs for communities, metrics, reviews, recommendations, comparisons, chat, and community reports.
- Cache-first metric refresh flow for rent, commute, grocery density, crime, noise, night activity, parking, and review signals.
- PostgreSQL persistence for communities, metrics, dimension scores, comparison results, and review posts.
- Rule-based scoring for safety, transit, convenience, parking, and environment.
- Weighted recommendation ranking based on user preference weights from the frontend or AI chat.
- Side-by-side community comparison with structured score differences and optional OpenAI-generated summary text.
- Community insight generation from metrics, review excerpts, and optional web-grounded context.
- Agent endpoints for community search, community discovery, community intake, community reports, web research, and preference extraction.
- Review ingestion and filtering support for YouTube and Google Maps review data.
- Seeded SQL snapshot path for quickly reproducing a working local database.

## Architecture

```mermaid
flowchart LR
  Frontend[RentWise Frontend<br/>React + Vite] --> Proxy[Vite /api proxy<br/>or VITE_API_BASE_URL]
  Proxy --> FastAPI[RentWise Backend<br/>FastAPI app/main.py]

  FastAPI --> Routes[API Routes<br/>health, communities, recommend,<br/>compare, chat, agent]

  Routes --> CommunitySvc[Community APIs<br/>list/detail/reviews/insight]
  Routes --> RecommendSvc[Recommend Service<br/>weighted ranking]
  Routes --> CompareSvc[Compare Service<br/>structured diff + summary]
  Routes --> AgentLayer[RentWiseAgent<br/>intent routing + skills]

  CommunitySvc --> Ingest[Ingest Service<br/>cache-first metrics and reviews]
  RecommendSvc --> Scoring[Scoring Service<br/>dimension scores + normalized weights]
  CompareSvc --> Scoring
  CommunitySvc --> Insight[Insight Service<br/>metric and review commentary]

  AgentLayer --> Skills[Skills<br/>community search, community report,<br/>web research, preference extraction]
  Skills --> Scoring
  Skills --> Database[(PostgreSQL)]

  Ingest --> Fetchers[Fetcher Integrations]
  Fetchers --> OSM[OpenStreetMap / Overpass<br/>grocery, noise proxy, parking]
  Fetchers --> Maps[Google Maps / OpenRouteService<br/>commute and place data]
  Fetchers --> YouTube[YouTube<br/>video comments]
  Fetchers --> Crime[CrimeGrade / Crimeometer<br/>local crime fallback]
  Fetchers --> VIIRS[NASA VIIRS local raster<br/>night activity]
  Fetchers --> Zillow[Zillow ZORI CSV<br/>rent baseline]

  CommunitySvc --> Database
  RecommendSvc --> Database
  CompareSvc --> Database
  Ingest --> Database
  Insight --> Database

  Database --> Tables[community<br/>community_metrics<br/>dimension_score<br/>community_comparison<br/>review_post]

  AgentLayer --> OpenAI[OpenAI<br/>chat routing, preference extraction,<br/>reports, summaries, web search]
  CompareSvc --> OpenAI
  Insight --> OpenAI
```

The backend is organized as a layered FastAPI application. `app/main.py` creates the app, configures CORS for local frontend ports, and registers route modules. Route handlers in `app/api/routes` keep request handling thin and delegate to service modules under `app/services`.

The database layer uses SQLAlchemy models and CRUD helpers under `app/db`. Community data is stored in PostgreSQL tables for base community records, metrics, computed dimension scores, saved comparison results, and review posts. The ingest service refreshes stale metrics using external fetchers when data is missing or expired, then stores the result for later frontend calls.

AI features are optional but enabled when `OPENAI_API_KEY` is configured. The regular `/chat` endpoint uses a chat service, while `/agent/*` routes use `RentWiseAgent`, `chat_agent.py`, and reusable skills to route user intent to community search, report generation, web research, or preference extraction.

Key backend files:

```text
app/
  main.py                  # FastAPI app, CORS, route registration
  api/routes/
    health.py              # service health endpoints
    communities.py         # community list/detail/reviews/insight APIs
    recommend.py           # weighted recommendation endpoint
    compare.py             # side-by-side comparison endpoint
    chat.py                # direct LLM preference chat endpoint
    agent.py               # agent search/report/chat/discovery endpoints
  services/
    ingest_service.py      # cache-first data refresh pipeline
    scoring_service.py     # score formulas and weight normalization
    recommend_service.py   # community ranking
    compare_service.py     # structured diffs and comparison summaries
    insight_service.py     # insight cards and web-grounded context
    review_filter_service.py
    fetchers/              # external data integrations
  agents/
    rentwise_agent.py      # agent orchestration
    chat_agent.py          # intent routing to skills
  skills/                  # community search/report/web/preference skills
  db/
    models.py              # SQLAlchemy table models
    crud.py                # database read/write helpers
    database.py            # engine/session setup
  schemas/                 # Pydantic request/response models
scripts/                   # seed and fetch scripts
sql/                       # schema and seeded data snapshots
docs/data_sources/         # source catalog and schemas
```

Primary request flow:

1. The frontend calls backend APIs through `/api` in local development.
2. FastAPI routes validate requests with Pydantic schemas.
3. Service modules load cached database records and refresh stale data when needed.
4. Scoring functions compute dimension scores and weighted recommendation totals.
5. Optional OpenAI calls generate natural-language chat replies, insights, reports, and comparison summaries.
6. Responses are returned as typed JSON consumed by the frontend.

## API

Interactive API docs are available after startup:

```text
http://127.0.0.1:8000/docs
```

Main endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service status |
| `GET` | `/health` | Health check |
| `GET` | `/communities` | List cached communities and metrics |
| `GET` | `/communities/{community_id}` | Community profile and metrics |
| `GET` | `/communities/{community_id}/reviews` | YouTube / Google Maps review posts |
| `GET` | `/communities/review-keyword-config` | Keyword configuration for frontend review filtering |
| `POST` | `/communities/{community_id}/insight` | Metric, review, and optional web-grounded insight cards |
| `POST` | `/recommend` | Rank communities from preference weights |
| `POST` | `/compare` | Compare two communities with structured scores and summary |
| `POST` | `/chat` | Direct LLM chat for preference extraction |
| `POST` | `/agent/chat` | Agent-routed chat for preference extraction, search, report, or web research |
| `POST` | `/agent/community-report` | Generate detailed community report |
| `POST` | `/agent/community-search` | Search for a community by name/city/state |
| `POST` | `/agent/community-discovery` | Discover and inspect a community using agent workflow |
| `POST` | `/agent/community-intake` | Create or resolve a community record for intake |

Example requests:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/communities
curl http://127.0.0.1:8000/communities/irvine-spectrum
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

```bash
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "community_a_id": "irvine-spectrum",
    "community_b_id": "woodbridge",
    "weights": {
      "safety": 30,
      "transit": 25,
      "convenience": 15,
      "parking": 20,
      "environment": 10
    }
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I care about safety and parking"}]}'
```

## Tech Stack

- Python 3.11
- FastAPI
- Uvicorn
- SQLAlchemy 2
- PostgreSQL 16
- Pydantic 2 and pydantic-settings
- OpenAI Python SDK
- Docker / Docker Compose
- External data integrations: OpenStreetMap / Overpass, Google Maps, OpenRouteService, YouTube, CrimeGrade / Crimeometer, NASA VIIRS, Zillow ZORI CSV

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/Lujixian2002/Rentwise.git
cd Rentwise/backend
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create environment file

Create `.env.local` in the backend repository root:

```env
DATABASE_URL=postgresql://rentwise_user:rentwise_password@localhost:5432/rentwise
APP_ENV=dev
METRICS_TTL_HOURS=24

# Optional, enables AI-generated chat, summaries, insights, reports, and filtering.
OPENAI_API_KEY=your_openai_api_key

# Optional, enables richer live data refreshes.
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
OPENROUTESERVICE_API_KEY=your_openrouteservice_api_key
YOUTUBE_API_KEY=your_youtube_api_key
CRIMEOMETER_API_KEY=your_crimeometer_api_key
NASA_EARTHDATA_TOKEN=your_nasa_earthdata_token
```

Configuration variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | SQLAlchemy URL for PostgreSQL |
| `APP_ENV` | No | Environment label |
| `METRICS_TTL_HOURS` | No | Cache TTL for community metrics |
| `OPENAI_API_KEY` | No | Enables LLM chat, comparison copy, insights, reports, web research, and review filtering |
| `OPENAI_WEB_SEARCH_MODEL` | No | Model override for web-grounded community info |
| `OPENAI_WEB_SEARCH_TIMEOUT_SEC` | No | Timeout for web-grounded community info |
| `OPENAI_REVIEW_FILTER_MODEL` | No | Model for AI review filtering |
| `GOOGLE_MAPS_API_KEY` | No | Commute times and place review signals |
| `OPENROUTESERVICE_API_KEY` | No | Commute fallback |
| `YOUTUBE_API_KEY` | No | YouTube comment ingestion |
| `CRIMEOMETER_API_KEY` | No | Crime rate API |
| `NASA_EARTHDATA_TOKEN` | No | VIIRS night-activity support |

Missing optional API keys are handled gracefully where possible. Related fetchers return `None` or fall back to cached/local data.

## How to Run Locally

### Option A: Docker Compose

Run backend and PostgreSQL together:

```bash
docker compose -f docker-compose.backend.yml up --build
```

Open:

```text
http://127.0.0.1:8000/docs
```

Stop the stack:

```bash
docker compose -f docker-compose.backend.yml down
```

### Option B: Local Python + local PostgreSQL

Start PostgreSQL, then import the seeded dataset:

```bash
docker run -d --name rentwise-postgres \
  -e POSTGRES_DB=rentwise \
  -e POSTGRES_USER=rentwise_user \
  -e POSTGRES_PASSWORD=rentwise_password \
  -p 5432:5432 \
  postgres:16
```

```bash
cat sql/1_create_tables.sql sql/2_insert_statements.sql | \
  docker exec -i -e PGPASSWORD=rentwise_password rentwise-postgres \
  psql -U rentwise_user -d rentwise
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/communities
```

## Seeded Dataset

The `sql/` folder includes a fast path for reproducing the shared project dataset without calling live external APIs.

| File | Contents |
| --- | --- |
| `sql/1_create_tables.sql` | Database schema |
| `sql/2_insert_statements.sql` | Seeded communities, metrics, dimension scores, and review posts |
| `sql/3_add_review_filter_cache.sql` | Review filter cache columns |
| `sql/test.sql` | Manual SQL checks |

To regenerate `sql/2_insert_statements.sql` after refreshing local data:

```bash
PYTHONPATH=. python sql/export_share_sql.py
```

## Data Refresh

For a full live refresh, run:

```bash
python -m scripts.fetch_irvine_sample
```

This creates tables, seeds base communities, and fetches sample metrics. It can take several minutes because it may call external APIs and read local data assets.

Local assets expected by some fetchers:

- Zillow ZORI CSV data under `data/`
- VIIRS night-light raster configured by `VIIRS_LOCAL_RADIANCE_TIF`

## Testing / Verification

There is no full automated test suite in this repository yet. Use these checks before final submission or demo:

```bash
python -m compileall app scripts
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/communities
```

Recommended manual verification:

1. Start PostgreSQL and the backend.
2. Load the seeded SQL files.
3. Open `http://127.0.0.1:8000/docs`.
4. Confirm `GET /health` returns an OK response.
5. Confirm `GET /communities` returns seeded communities.
6. Confirm `POST /recommend` returns ranked communities.
7. Confirm `POST /compare` returns structured score differences.
8. Confirm `GET /communities/{community_id}/reviews` returns review posts for seeded communities.
9. If `OPENAI_API_KEY` is configured, confirm `/agent/chat`, `/agent/community-report`, and `/communities/{community_id}/insight` return AI-assisted responses.

## Deployment Status

Current status: the RentWise frontend is deployed, and the backend supports local development, Docker Compose execution, and hosted integration with the deployed frontend.

- Local FastAPI server: supported.
- Local Docker Compose with PostgreSQL: supported.
- Seeded local database reproduction: supported.
- Live frontend deployment: https://rentwise-cod.pages.dev/
- Frontend integration: supported through Vite `/api` proxy or `VITE_API_BASE_URL`.

## Demo Video

Final demo video:

```text
https://drive.google.com/file/d/1BufoYp1h5vMAkXCaezZZxoiZ-KXkTJWT/view?usp=sharing
```

## Known Issues / Future Work

- Full live data refresh depends on optional external API keys and local data assets.
- OpenAI-powered endpoints require `OPENAI_API_KEY`; fallback behavior exists for several flows but AI-generated text will be limited without it.
- Docker Compose starts an empty PostgreSQL database; import the seeded SQL snapshot for a ready-to-demo dataset.
- Free-tier hosted backend instances may have cold-start latency after idle periods.
- Future work: add automated API tests for route responses and scoring behavior.
- Future work: add migration tooling instead of relying on raw SQL snapshots.
- Future work: add scheduled refresh jobs for metrics and reviews.

## Useful Commands

```bash
uvicorn app.main:app --reload --port 8000      # Start local API server
docker compose -f docker-compose.backend.yml up --build
docker compose -f docker-compose.backend.yml down
python -m scripts.seed_communities             # Seed base community records
python -m scripts.fetch_irvine_sample          # Fetch sample metrics and reviews
PYTHONPATH=. python sql/export_share_sql.py    # Export seeded SQL snapshot
```

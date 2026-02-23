from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import communities, compare, health
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Rentwise Backend", version="0.1.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(communities.router, prefix="/communities", tags=["communities"])
app.include_router(compare.router, prefix="/compare", tags=["compare"])


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "rentwise-backend", "status": "ok"}

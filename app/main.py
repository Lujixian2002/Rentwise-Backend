from fastapi import FastAPI

from app.api.routes import communities, compare, health
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Rentwise Backend", version="0.1.0")

app.include_router(health.router)
app.include_router(communities.router, prefix="/communities", tags=["communities"])
app.include_router(compare.router, prefix="/compare", tags=["compare"])


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "rentwise-backend", "status": "ok"}

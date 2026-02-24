from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Community
from app.services.fetchers.geocoding import geocode_community


def resolve_community(
    db: Session,
    community_id: str | None = None,
    community_name: str | None = None,
    allow_external_lookup: bool = True,
) -> Community | None:
    if community_id:
        row = crud.get_community(db, community_id)
        if row:
            return row

    if community_name:
        row = crud.get_community_by_name(db, community_name)
        if row:
            return row

        if allow_external_lookup:
            geocoded = geocode_community(community_name)
            if geocoded:
                return crud.create_community(
                    db=db,
                    name=str(geocoded.get("name") or community_name.strip()),
                    city=_as_str(geocoded.get("city")),
                    state=_as_str(geocoded.get("state")),
                    center_lat=_as_float(geocoded.get("lat")),
                    center_lng=_as_float(geocoded.get("lng")),
                )
    return None


def resolve_coords(db: Session, community_id: str | None = None, community_name: str | None = None) -> tuple[float, float] | None:
    row = resolve_community(db, community_id=community_id, community_name=community_name)
    if row is None or row.center_lat is None or row.center_lng is None:
        return None
    return row.center_lat, row.center_lng


def _as_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

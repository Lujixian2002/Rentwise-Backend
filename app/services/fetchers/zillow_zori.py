from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


DEFAULT_ZORI_PATH = "data/City_zori_uc_sfrcondomfr_sm_month.csv"
DEFAULT_CITY = "Irvine"
DEFAULT_STATE = "CA"

# Current sample communities are all Irvine sub-areas.
DEFAULT_COMMUNITY_IDS = (
    "irvine-spectrum",
    "woodbridge",
    "university-town-center",
    "turtle-rock",
)


def read_zori_rows(
    path: str = DEFAULT_ZORI_PATH,
    city: str = DEFAULT_CITY,
    state: str = DEFAULT_STATE,
    community_ids: Iterable[str] = DEFAULT_COMMUNITY_IDS,
) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        date_columns = [name for name in (reader.fieldnames or []) if _is_date_column(name)]
        if not date_columns:
            return []

        city_row = _find_city_row(reader, city=city, state=state)
        if not city_row:
            return []

        latest_rent, rent_12m_ago = _extract_latest_and_12m_ago(city_row, date_columns)
        rent_trend_12m_pct = None
        if latest_rent is not None and rent_12m_ago is not None and rent_12m_ago > 0:
            rent_trend_12m_pct = round(((latest_rent / rent_12m_ago) - 1.0) * 100.0, 2)

        rows: list[dict[str, str]] = []
        for community_id in community_ids:
            rows.append(
                {
                    "community_id": community_id,
                    "median_rent": _to_str(latest_rent),
                    "rent_2b2b": "",
                    "rent_1b1b": "",
                    "avg_sqft": "",
                    "rent_trend_12m_pct": _to_str(rent_trend_12m_pct),
                }
            )
        return rows


def _find_city_row(reader: csv.DictReader, city: str, state: str) -> dict[str, str] | None:
    city_lower = city.strip().lower()
    state_upper = state.strip().upper()
    for row in reader:
        if (row.get("RegionType") or "").strip().lower() != "city":
            continue
        if (row.get("RegionName") or "").strip().lower() != city_lower:
            continue
        if (row.get("State") or "").strip().upper() != state_upper:
            continue
        return row
    return None


def _extract_latest_and_12m_ago(row: dict[str, str], date_columns: list[str]) -> tuple[float | None, float | None]:
    values = [_to_float(row.get(col)) for col in date_columns]
    latest_idx = None
    for i in range(len(values) - 1, -1, -1):
        if values[i] is not None:
            latest_idx = i
            break
    if latest_idx is None:
        return None, None

    latest = values[latest_idx]
    prev_idx = latest_idx - 12
    prev_12m = values[prev_idx] if prev_idx >= 0 else None
    return latest, prev_12m


def _is_date_column(name: str) -> bool:
    # Zillow monthly columns are like 2025-12-31.
    parts = name.split("-")
    if len(parts) != 3:
        return False
    return len(parts[0]) == 4 and parts[0].isdigit()


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_str(value: float | None) -> str:
    if value is None:
        return ""
    return str(value)

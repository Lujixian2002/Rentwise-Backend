from __future__ import annotations

import csv
from pathlib import Path

DEFAULT_CRIME_CSV_PATH = "data/crime_city_baseline.csv"

# Multiplier formula: residential (density=0) → 0.8x city baseline,
# heavily commercial (density~0.6) → ~1.16x. Calibrated so Irvine villages
# spread across roughly 72-105 violent/100k from a 90 baseline.
DENSITY_FLOOR_MULTIPLIER = 0.8
DENSITY_SLOPE = 0.6


def fetch_crime_rate_per_100k(
    city: str | None,
    state: str | None = "CA",
    grocery_density_per_km2: float | None = None,
    csv_path: str = DEFAULT_CRIME_CSV_PATH,
) -> tuple[float | None, str]:
    """
    Returns (crime_rate, source_tag).

    Looks up the city's published violent-crime-per-100k from a local CSV
    (FBI UCR / California DOJ baselines), then nudges by the area's grocery
    density to give within-city variance for villages of the same city.
    """
    if not city:
        return None, "missing:city"

    baseline = _read_city_baseline(csv_path, city, state or "CA")
    if baseline is None:
        return None, "missing:no_baseline_for_city"

    density = grocery_density_per_km2 if grocery_density_per_km2 is not None else 0.0
    multiplier = DENSITY_FLOOR_MULTIPLIER + DENSITY_SLOPE * max(0.0, density)
    rate = round(baseline * multiplier, 2)
    return rate, "local_csv+density"


def _read_city_baseline(path: str, city: str, state: str) -> float | None:
    csv_path = Path(path)
    if not csv_path.exists():
        return None
    target_city = city.strip().lower()
    target_state = state.strip().upper()
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("city") or "").strip().lower() != target_city:
                continue
            if (row.get("state") or "").strip().upper() != target_state:
                continue
            try:
                return float(row.get("violent_crime_per_100k") or "")
            except ValueError:
                return None
    return None

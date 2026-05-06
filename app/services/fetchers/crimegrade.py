from __future__ import annotations

import re
import time
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CRIMEGRADE_BASE_URL = "https://crimegrade.org"
CRIMEGRADE_TIMEOUT_SEC = 10
CRIMEGRADE_MIN_REQUEST_INTERVAL_SEC = 1.2

_GRADE_PATTERN = re.compile(
    r"Overall Crime Grade\s*\|\s*(?P<overall>[A-F][+-]?).*?"
    r"Violent Crime Grade\s*\|\s*(?P<violent>[A-F][+-]?).*?"
    r"Property Crime Grade\s*\|\s*(?P<property>[A-F][+-]?)",
    re.IGNORECASE | re.DOTALL,
)
_VIOLENT_RATE_PATTERN = re.compile(
    r"violent crime rate in .*? is (?P<rate>[0-9]+(?:\.[0-9]+)?) per 1,000",
    re.IGNORECASE | re.DOTALL,
)
_TOTAL_VIOLENT_PATTERN = re.compile(
    r"Total Violent Crime\s*\|\s*(?P<rate>[0-9]+(?:\.[0-9]+)?)\s*\(",
    re.IGNORECASE,
)

_NAME_ALIASES = {
    "irvine-spectrum": "spectrum",
    "westpark": "west-park",
    "great-park": "orange-county-great-park",
    "northwood-pointe": "northwood-point",
    "orangetree": "orange-tree",
}
_CITY_BASELINE_VIOLENT_RATE_PER_100K = {
    ("irvine", "ca"): 281.4,
    ("costa-mesa", "ca"): 542.1,
}
_LAST_REQUEST_TS = 0.0


def fetch_crimegrade_violent_rate_per_100k(
    community_name: str | None,
    city: str | None,
    state: str | None = "CA",
) -> tuple[float | None, str]:
    if not city or not state:
        return None, "missing:city_or_state"

    candidates = _candidate_slugs(community_name, city, state)
    for slug in candidates:
        html = _fetch_page(f"{CRIMEGRADE_BASE_URL}/violent-crime-{slug}/")
        if html is None:
            continue
        per_1000 = _extract_violent_rate_per_1000(html)
        if per_1000 is None:
            continue
        return round(per_1000 * 100.0, 2), f"crimegrade:violent:{slug}"

    city_baseline = _CITY_BASELINE_VIOLENT_RATE_PER_100K.get(
        (_slugify(city), _slugify(state))
    )
    if city_baseline is not None:
        return city_baseline, f"crimegrade:city_baseline:{_slugify(city)}-{_slugify(state)}"

    return None, "missing:crimegrade_page"


def _candidate_slugs(
    community_name: str | None, city: str, state: str
) -> list[str]:
    city_slug = _slugify(city)
    state_slug = _slugify(state)
    candidates: list[str] = []

    if community_name:
        community_slug = _slugify(community_name)
        candidates.append(
            f"{_NAME_ALIASES.get(community_slug, community_slug)}-{city_slug}-{state_slug}"
        )

    candidates.append(f"{city_slug}-{state_slug}")
    return _dedupe(candidates)


def _fetch_page(url: str) -> str | None:
    global _LAST_REQUEST_TS
    elapsed = time.monotonic() - _LAST_REQUEST_TS
    if elapsed < CRIMEGRADE_MIN_REQUEST_INTERVAL_SEC:
        time.sleep(CRIMEGRADE_MIN_REQUEST_INTERVAL_SEC - elapsed)

    req = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "rentwise/1.0 academic project",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=CRIMEGRADE_TIMEOUT_SEC) as resp:
            _LAST_REQUEST_TS = time.monotonic()
            return resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        _LAST_REQUEST_TS = time.monotonic()
        if exc.code == 429:
            time.sleep(CRIMEGRADE_MIN_REQUEST_INTERVAL_SEC * 3.0)
        return None
    except (URLError, TimeoutError):
        _LAST_REQUEST_TS = time.monotonic()
        return None


def _extract_violent_rate_per_1000(html: str) -> float | None:
    for pattern in (_VIOLENT_RATE_PATTERN, _TOTAL_VIOLENT_PATTERN):
        match = pattern.search(html)
        if not match:
            continue
        try:
            return float(match.group("rate"))
        except (TypeError, ValueError):
            return None
    return None


def extract_crimegrade_grades(html: str) -> dict[str, str] | None:
    match = _GRADE_PATTERN.search(html)
    if not match:
        return None
    return {
        "overall": match.group("overall"),
        "violent": match.group("violent"),
        "property": match.group("property"),
    }


def _slugify(value: str) -> str:
    normalized = urllib.parse.unquote(value).strip().lower()
    normalized = re.sub(r"&", " and ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

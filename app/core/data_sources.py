from dataclasses import dataclass


@dataclass(frozen=True)
class DataSource:
    dimension: str
    source: str
    official_url: str
    required: bool
    note: str


CORE_DATA_SOURCES: tuple[DataSource, ...] = (
    DataSource(
        dimension="Rental Location / Price / Unit Type",
        source="Craigslist / Zillow Listings",
        official_url="https://www.craigslist.org / https://www.zillow.com",
        required=True,
        note="Base listing geolocation + rental metrics",
    ),
    DataSource(
        dimension="Commute Time",
        source="Google Maps Distance Matrix API / OpenRouteService",
        official_url=(
            "https://developers.google.com/maps/documentation/distance-matrix / "
            "https://openrouteservice.org"
        ),
        required=True,
        note="Transit and driving time to destination (campus/work)",
    ),
    DataSource(
        dimension="Grocery Density",
        source="OpenStreetMap Overpass API / Yelp Fusion API",
        official_url="https://www.openstreetmap.org / https://www.yelp.com/developers",
        required=True,
        note="Nearby grocery and supermarket density",
    ),
    DataSource(
        dimension="Crime Rate",
        source="City of Irvine Open Data (Socrata)",
        official_url="https://data.cityofirvine.org",
        required=True,
        note="City-level safety signal",
    ),
    DataSource(
        dimension="Rent Trend",
        source="Zillow Research Data (ZORI)",
        official_url="https://www.zillow.com/research/data/",
        required=True,
        note="Long-term rent stability and growth trend",
    ),
    DataSource(
        dimension="Nighttime Activity Proxy",
        source="NASA VIIRS Nighttime Lights",
        official_url="https://earthdata.nasa.gov",
        required=True,
        note="Urban activity proxy for nightlife and vitality",
    ),
    DataSource(
        dimension="Noise Exposure",
        source="OpenStreetMap (highway/airport proximity)",
        official_url="https://www.openstreetmap.org",
        required=True,
        note="Quality-of-life indicator often missing from listing platforms",
    ),
    DataSource(
        dimension="Review Signals",
        source="Reddit API / forum sources",
        official_url="https://www.reddit.com/dev/api/",
        required=True,
        note="Unstructured sentiment turned into structured review signals",
    ),
)


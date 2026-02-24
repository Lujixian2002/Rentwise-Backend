# Data Source Catalog

## 汇报速览：数据源与指标映射

| Data Source | Type | How We Fetch | Used For Metrics | Current Status |
|---|---|---|---|---|
| Zillow ZORI City CSV | CSV | Local file parse (`zillow_zori.py`) | `median_rent`, `rent_trend_12m_pct` | partial |
| OpenStreetMap Overpass API | API | HTTP query (`overpass_osm.py`) | `grocery_density_per_km2`, `night_activity_index`, `noise_avg_db`, `noise_p90_db` | partial |
| Crimeometer | API | HTTP query (`irvine_crime.py`) | `crime_rate_per_100k` | partial |
| Google Distance Matrix | API | Placeholder (`google_maps.py`) | `commute_minutes` (planned) | planned |
| OpenRouteService | API | Placeholder (`openrouteservice.py`) | `commute_minutes` fallback (planned) | planned |
| Reddit / Forums | API | Not implemented | `review_signal_score` (planned) | planned |

## 数据源目录（按维度）

| Dimension | Primary Source | Type | URL | Secondary Source | Type | URL | Current Status |
|---|---|---|---|---|---|---|---|
| Rental location / rent / unit type | Zillow Listings / local file | CSV | local `data/City_zori_uc_sfrcondomfr_sm_month.csv` | Craigslist Listings | API | https://www.craigslist.org | partial |
| Commute time | Google Distance Matrix API | API | https://developers.google.com/maps/documentation/distance-matrix | OpenRouteService | API | https://openrouteservice.org | planned |
| Grocery density | OpenStreetMap Overpass API | API | https://www.openstreetmap.org | Yelp Fusion API | API | https://www.yelp.com/developers | partial |
| Crime rate | Crimeometer | API | https://www.crimeometer.com/ | FBI CDE | API | https://cde.ucr.cjis.gov | partial |
| Rent trend | Zillow Research Data (ZORI) | CSV | local `data/City_zori_uc_sfrcondomfr_sm_month.csv` | Zillow Research Dataset | CSV | https://www.zillow.com/research/data/ | partial |
| Nighttime activity proxy | OSM amenity proxy (current) | API | https://www.openstreetmap.org | NASA VIIRS (target) | API | https://earthdata.nasa.gov | partial |
| Noise exposure | OSM highway/airport proximity | API | https://www.openstreetmap.org | - | - | - | partial |
| Review signals | Reddit API / forums | API | https://www.reddit.com/dev/api/ | - | - | - | planned |

## Notes

- `partial`: 已接入基础抓取，但稳定性/覆盖率仍需增强。
- `planned`: 仅有占位逻辑或尚未接入。
- 对需要 API key 的来源，密钥统一放 `.env`，不提交到仓库。

# Data Schemas and Field Formats

## 0) 获取方式与输出指标映射（汇报用）

| Source | Fetcher / Method | Raw Input | Output Metric(s) | DB Field(s) |
|---|---|---|---|---|
| Zillow ZORI City CSV | `read_zori_rows()` in `zillow_zori.py` | `RegionName/RegionType/State/时间序列列` | 最新租金、12个月趋势 | `median_rent`, `rent_trend_12m_pct` |
| VIIRS Night Lights (local tif) | `fetch_viirs_night_activity_index()` in `nasa_viirs.py` | `avg_radiance.tif` + community lat/lng | Night activity index | `night_activity_index` |
| OSM Overpass | `fetch_grocery_density()` | `lat,lng,radius` | Grocery density | `grocery_density_per_km2` |
| OSM Overpass | `fetch_night_activity_index()` | `lat,lng,radius` | Night activity proxy | `night_activity_index` |
| OSM Overpass | `fetch_noise_proxy()` | `lat,lng,radius` | Noise proxy | `noise_avg_db`, `noise_p90_db` |
| Crimeometer API | `fetch_crime_rate_per_100k_with_source()` | `lat,lng,radius,datetime range` | Crime rate per 100k | `crime_rate_per_100k` |
| Google Maps / ORS | Placeholder | `origin,destination` | Commute minutes | planned (`commute_minutes`) |
| Reddit / Forums | Not implemented | text posts | Review signal score | planned (`review_signal_score`) |

## 1) ZORI CSV (`data/City_zori_uc_sfrcondomfr_sm_month.csv`)


> Rent trend is modeled at the city level due to data granularity and stability considerations. While smaller geographic units such as ZIP codes provide finer detail, they often suffer from higher volatility, incomplete time series, and limited sample sizes, which can reduce reliability. City-level ZORI data offers a more stable and consistent long-term rental trend, making it suitable for evaluating overall market direction and contract risk. Community-level comparisons are primarily differentiated using localized indicators such as safety, convenience, and noise, while rent trend serves as a macro-level stability signal.


### Input Columns
| Column | Type | Required | Example |
|---|---|---|---|
| `RegionName` | string | yes | `Irvine` |
| `RegionType` | string | yes | `city` |
| `State` | string | yes | `CA` |
| `YYYY-MM-DD` month columns | float | no | `3400.22` |

### Mapped DB Fields
- `community_metrics.median_rent`
- `community_metrics.rent_trend_12m_pct`

### Transform Rule (Current Implementation)
- 过滤 `RegionType=city`, `RegionName=Irvine`, `State=CA`。
- `median_rent` = 最新一个非空月值。
- `rent_trend_12m_pct` = `(latest / 12个月前 - 1) * 100`。
- 输出会映射到当前社区样本 ID（如 `irvine-spectrum`, `woodbridge`）。

## 2) Overpass OSM

### Fetcher Outputs
| Function | Output | DB Mapping |
|---|---|---|
| `fetch_grocery_density(...)` | `float | None` | `community_metrics.grocery_density_per_km2` |
| `fetch_night_activity_index(...)` | `float | None` (0-100) | `community_metrics.night_activity_index` |
| `fetch_noise_proxy(...)` | `(noise_avg_db, noise_p90_db)` | `community_metrics.noise_avg_db`, `community_metrics.noise_p90_db` |

### Null Semantics
- 返回 `None` 表示请求失败、超时、限流或未找到有效要素。

## 3) Crime Rate (Crimeometer)

### Fetcher Output
| Function | Output | DB Mapping |
|---|---|---|
| `fetch_crime_rate_per_100k_with_source(city, center_lat, center_lng)` | `(float | None, str)` | `community_metrics.crime_rate_per_100k` |

### Current Limitation
- 事件计数转 `per_100k` 目前使用局部人口密度估算（非 census 精确人口）。

## 4) Scoring Inputs (Service Internal)

`app/services/scoring_service.py` 预期输入字段：
- `median_rent`
- `commute_minutes`
- `grocery_density_per_km2`
- `crime_rate_per_100k`
- `rent_trend_12m_pct`
- `noise_avg_db`
- `night_activity_index`
- `review_signal_score`

缺失字段将使用默认值计算，确保流程可运行。

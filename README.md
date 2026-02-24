# RentWise Backend

RentWise 是一个社区级（community-level）的租房决策支持后端。系统聚合结构化指标与代理信号，输出可解释的社区指标、维度分数和社区对比结果。

本项目不处理和存储用户个人隐私信息（PII）。

## 1. 项目简介（What / Why）

### What
- 提供 FastAPI 接口获取社区指标与比较结果。
- 通过缓存优先（cache-first）策略抓取并持久化外部数据。
- 产出以下核心数据：
  - `community_metrics`
  - `dimension_score`
  - `community_comparison`

### Why
- 传统租房平台常缺少“生活质量”与“长期趋势”维度。
- 本项目将租金、犯罪、便利性、噪音、夜间活跃度等信号整合为统一评分，用于更稳健的租房决策。

## 2. 核心能力与当前范围

### In Scope（当前已实现）
- FastAPI 基础接口：`/health`、`/communities/{id}`、`/compare`
- 社区初始化脚本：`scripts/seed_communities.py`
- 样本抓取与入库脚本：`scripts/fetch_irvine_sample.py`
- ZORI 本地 CSV 读取（租金/趋势基线）
- Overpass 抓取尝试：
  - grocery density
  - night activity proxy
  - noise proxy（高速/机场邻近度）
- Crimeometer crime 抓取（按经纬度半径查询）
- 维度评分计算与 `dimension_score` 持久化
- 社区比较结果持久化到 `community_comparison`

### Out of Scope（当前未完成）
- 通勤真实 API 接入（Google Distance Matrix / OpenRouteService）
- Review pipeline（Reddit/论坛文本抽取与结构化信号）
- `community_context` 原始 payload 完整落库
- 更稳健的重试/退避/监控与质量度量

## 3. 系统架构与分层职责

### API Layer
- 路由入口与 HTTP 协议处理。
- 文件：`app/api/routes/*`, `app/main.py`

### Service Layer
- `ingest_service.py`：TTL 检查 + 抓取 + 回填 + 评分落库
- `scoring_service.py`：维度分数计算（0-100）
- `compare_service.py`：A/B 社区比较、差异结构化、摘要与权衡

### Fetcher Layer
- `app/services/fetchers/*`：外部数据源调用与数据转换

### Data Layer
- ORM：`app/db/models.py`
- CRUD：`app/db/crud.py`
- DB 引擎/Session：`app/db/database.py`

### Utils Layer
- `app/utils/geo.py`：地理计算
- `app/utils/time.py`：TTL 相关工具

### 请求到返回的数据流（文字流程）
1. API 接收请求。
2. Service 检查缓存是否过期（`updated_at` + TTL）。
3. 若缺失/过期，调用 fetchers 抓取外部数据。
4. 写入 `community_metrics`，并计算写入 `dimension_score`。
5. compare 请求再基于两社区分数生成 `structured_diff/tradeoffs`，落 `community_comparison`。
6. 返回结构化响应（允许部分字段为 `null`）。

## 4. 目录结构详解

```text
rentwise-backend/
├── app/
│   ├── main.py                      # FastAPI app entry
│   ├── core/
│   │   ├── config.py                # 环境变量配置
│   │   ├── logging.py               # 日志初始化
│   │   └── data_sources.py          # 数据源映射定义
│   ├── db/
│   │   ├── database.py              # engine/session/Base
│   │   ├── models.py                # ORM models
│   │   └── crud.py                  # DB helpers
│   ├── schemas/
│   │   ├── community.py             # 社区响应模型
│   │   └── comparison.py            # 比较请求/响应模型
│   ├── services/
│   │   ├── fetchers/
│   │   │   ├── google_maps.py
│   │   │   ├── openrouteservice.py
│   │   │   ├── overpass_osm.py
│   │   │   ├── irvine_crime.py
│   │   │   └── zillow_zori.py
│   │   ├── ingest_service.py        # 抓取与回填编排
│   │   ├── scoring_service.py       # 评分逻辑
│   │   └── compare_service.py       # 社区比较逻辑
│   ├── api/
│   │   ├── routes/
│   │   │   ├── communities.py
│   │   │   ├── compare.py
│   │   │   └── health.py
│   │   └── deps.py                  # DB session dependency
│   └── utils/
│       ├── geo.py
│       └── time.py
├── scripts/
│   ├── seed_communities.py          # 初始化社区数据
│   └── fetch_irvine_sample.py       # 抓取尔湾样本并写入数据库
├── data/
│   └── zori.csv                     # 本地租金趋势示例数据
├── schema.sql                       # 全量数据库设计草案
├── .env                             # 环境变量
├── requirements.txt                 # Python 依赖
└── README.md
```

重点文件说明：
- `scripts/fetch_irvine_sample.py`：一键建表、seed、触发抓取并打印入库结果。
- `scripts/seed_communities.py`：插入初始尔湾社区样本。
- `data/zori.csv`：当前 rent/trend 的本地基线来源。
- `.env`：数据库与 API key 配置。
- `requirements.txt`：运行后端与抓取逻辑所需依赖。

## 5. 数据模型与表职责

### 当前 ORM 已覆盖
- `community`：社区基本信息（名称、城市、中心点等）
- `community_metrics`：聚合指标（rent/crime/grocery/noise/night 等）
- `dimension_score`：每个社区每个维度的 0-100 分数
- `community_comparison`：A/B 比较结果（diff、summary、tradeoffs）

### schema 设计中但尚未全量接入 ORM/流程
- `community_context`：外部 API 原始 payload
- `review_post`：论坛/社区帖子原文
- `review_signal`：从帖子抽取的结构化信号

### 说明
- `schema.sql` 是全量数据库设计。
- 当前代码中的 ORM 覆盖的是核心闭环（metrics/score/comparison），并未覆盖全部表。

## 6. 关键数据流

### A) `GET /communities/{community_id}`
1. 查询 `community` 是否存在。
2. 调用 `ensure_metrics_fresh`：
   - 未命中或 TTL 过期 -> 抓取并回填 `community_metrics`
   - 命中且新鲜 -> 直接复用缓存
3. 返回 `community + metrics`。

说明：当前返回中 metrics 字段可能为 `null` 或部分子字段为 `null`（外部 API 超时/空响应时）。

### B) `POST /compare`
1. 校验 A/B 不相同。
2. 确保 A/B 两社区 metrics 新鲜（必要时触发回填）。
3. 读取 metrics 并计算维度分。
4. 生成 `structured_diff` 与 `tradeoffs`。
5. 写入 `community_comparison` 并返回结果。

## 7. API 说明

### `GET /health`
检查服务可用性。

```bash
curl http://127.0.0.1:8000/health
```

### `GET /communities/{community_id}`
获取社区基础信息与指标。

```bash
curl http://127.0.0.1:8000/communities/irvine-spectrum
```

### `POST /compare`
比较两个社区。

```bash
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "community_a_id": "irvine-spectrum",
    "community_b_id": "woodbridge",
    "weights": {
      "Safety": 1.2,
      "Transit": 1.5
    }
  }'
```

说明：当某些维度源数据不可用时，评分逻辑会使用默认值，返回结构中对应原始指标可能为 `null`。

## 8. 配置与环境变量

`.env` 关键字段：
- `DATABASE_URL`：SQLAlchemy 数据库连接
- `APP_ENV`：运行环境标识（如 `dev`）
- `METRICS_TTL_HOURS`：缓存 TTL（小时）
- `GOOGLE_MAPS_API_KEY`：Google 通勤 API
- `OPENROUTESERVICE_API_KEY`：ORS 通勤 API
- `CRIMEOMETER_API_KEY`：Crimeometer API key（crime 数据）
- `CRIMEOMETER_RADIUS_MILES`：crime 查询半径（英里）
- `CRIMEOMETER_LOOKBACK_DAYS`：crime 回看时间窗口（天）
- `YELP_API_KEY`：Yelp API
- `NASA_EARTHDATA_TOKEN`：NASA EarthData token
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`：Review pipeline 预留

Docker Postgres 示例（与你当前容器一致）：

```env
DATABASE_URL=postgresql+psycopg2://rentwise_user:ddbswdjx@localhost:5432/rentwise
```

## 9. 本地运行与 Docker Postgres 联调

请从项目根目录执行命令（非常重要，避免 `No module named app`）。

### 启动数据库（示例）
```bash
docker run -d \
  --name rentwise-postgres \
  -e POSTGRES_DB=rentwise \
  -e POSTGRES_USER=rentwise_user \
  -e POSTGRES_PASSWORD=ddbswdjx \
  -p 5432:5432 \
  -v rentwise_pgdata:/var/lib/postgresql/data \
  postgres:16
```

### conda 方式运行（推荐）
```bash
cd "/Users/lujixian/Documents/Courses/295P Keystone Project/Rentwise-Backend"
conda activate rentwise
python -m pip install -r requirements.txt
python -m scripts.fetch_irvine_sample
uvicorn app.main:app --reload
```

## 10. 数据抓取与样本入库脚本

### `scripts/seed_communities.py`
- 作用：只做社区基础数据初始化。
- 典型用途：首次建表后插入默认社区。

### `scripts/fetch_irvine_sample.py`
- 作用：
  1. 建表（基于当前 ORM）
  2. seed 社区
  3. 强制触发样本抓取（`ttl_hours=0`）
  4. 打印 `community_metrics` 与 `dimension_score` 入库统计

说明：外部 API 的不稳定性可能导致部分字段空值，这是当前阶段可接受行为。

## SQL 共享（团队协作）

项目已提供 `sql/` 目录用于共享结构和样本数据：
- `sql/1_create_tables.sql`
- `sql/2_insert_statements.sql`

导出当前数据库为可共享 SQL：

```bash
python -m scripts.export_share_sql --output sql/2_insert_statements.sql
```

## 11. 调试指南（常见报错）

### 问题 1：`ModuleNotFoundError: No module named 'sqlalchemy'`
```bash
conda activate rentwise
python -m pip install -r requirements.txt
python -m pip show sqlalchemy
```

### 问题 2：`ModuleNotFoundError: No module named 'app'`
```bash
cd "/Users/lujixian/Documents/Courses/295P Keystone Project/Rentwise-Backend"
python -m scripts.fetch_irvine_sample
```

### 问题 3：数据库连接失败
```bash
docker ps | grep rentwise-postgres
cat .env | grep DATABASE_URL
python -c "from app.db.database import engine; print(engine.url)"
```

### 问题 4：Overpass/Crimeometer 返回空导致指标缺失
```bash
python -m scripts.fetch_irvine_sample
# 若输出某些指标为 None，通常是外部 API 超时/限流/字段不匹配
# 可重复运行或后续增加重试与固定 endpoint
```

## 12. 扩展指南

### 新增 fetcher 约定
- 输入：尽量用明确地理参数（`lat/lng`、`radius_km`）与上下文（`city`）。
- 输出：
  - 成功返回标准化数值/结构
  - 不可用返回 `None`（不要抛未处理异常）
- 接入位置：`app/services/ingest_service.py` 的 `ensure_metrics_fresh`。

### 新增维度接入步骤
1. 在 `community_metrics` 增加字段（模型 + 表结构）。
2. 在 `ingest_service` 写入该字段。
3. 在 `scoring_service` 增加维度打分逻辑。
4. 在 `compare_service` 接入该维度比较。
5. 更新 README 的维度与 API 说明。

## 13. 当前实现状态与 Roadmap

### 短期
- 引入 census/tract 级人口数据，替换当前 crime per100k 的密度估算
- Overpass 增加重试/退避
- 将原始 API payload 写入 `community_context`

### 中期
- 接入 Google/ORS 通勤时间
- 接入 review signal pipeline（post -> signal）
- 优化缓存命中下的延迟与观测性

## 数据维度优先级（当前目标）

1. Rental location / rent / unit type
2. Commute time
3. Grocery density
4. Crime rate
5. Rent trend
6. Nighttime activity proxy
7. Noise exposure
8. Review signals

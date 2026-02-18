-- =========================
-- 1) COMMUNITY
-- =========================
CREATE TABLE community (
  community_id      varchar(64) PRIMARY KEY,
  name              varchar(255) NOT NULL,
  city              varchar(128),
  state             varchar(64),
  center_lat        numeric(10, 7),
  center_lng        numeric(10, 7),
  boundary_geojson  text,
  updated_at        timestamp
);

-- =========================
-- 2) COMMUNITY_METRICS (1:1 with community)
-- PK is also the FK in your ER, but we do NOT enforce FK here.
-- =========================
CREATE TABLE community_metrics (
  community_id             varchar(64) PRIMARY KEY,
  updated_at               timestamp,

  median_rent              double precision,
  rent_2b2b                double precision,
  rent_1b1b                double precision,
  avg_sqft                 double precision,

  grocery_density_per_km2  double precision,
  crime_rate_per_100k      double precision,
  rent_trend_12m_pct       double precision,
  night_activity_index     double precision,
  noise_avg_db             double precision,
  noise_p90_db             double precision,

  overall_confidence       double precision,
  details_json             text
);

-- =========================
-- 3) COMMUNITY_CONTEXT (1:n)
-- =========================
CREATE TABLE community_context (
  context_id     varchar(64) PRIMARY KEY,
  community_id   varchar(64) NOT NULL,
  updated_at     timestamp,
  context_type   varchar(32),   -- poi|crime|rent_trend|noise|night|commute|other
  source_name    varchar(128),
  json_payload   text
);

-- =========================
-- 4) REVIEW_POST (1:n)
-- =========================
CREATE TABLE review_post (
  post_id       varchar(64) PRIMARY KEY,
  community_id  varchar(64) NOT NULL,
  platform      varchar(32),    -- reddit|nextdoor|forum|other
  external_id   varchar(128),
  url           text,
  posted_at     timestamp,
  title         text,
  body_text     text
);

-- Optional (recommended): prevent duplicate crawls per platform
-- If you truly want zero constraints beyond PK, remove this.
CREATE UNIQUE INDEX ux_review_post_platform_external
  ON review_post(platform, external_id)
  WHERE external_id IS NOT NULL;

-- =========================
-- 5) REVIEW_SIGNAL (1:n from review_post)
-- =========================
CREATE TABLE review_signal (
  signal_id      varchar(64) PRIMARY KEY,
  post_id        varchar(64) NOT NULL,
  aspect         varchar(32),   -- noise|safety|management|parking|breakins|party|transit|grocery|other
  sentiment      varchar(8),    -- neg|neu|pos
  severity       double precision,
  confidence     double precision,
  evidence_text  text
);

-- =========================
-- 6) DIMENSION_SCORE (1:n from community)
-- =========================
CREATE TABLE dimension_score (
  score_id      varchar(64) PRIMARY KEY,
  community_id  varchar(64) NOT NULL,
  dimension     varchar(32),    -- Cost|Transit|Convenience|Parking|Safety|Trend|Nightlife|Noise|Reviews
  score_0_100   double precision,
  summary       text,
  details_json  text,
  data_origin   varchar(16),    -- api|ai|mixed
  updated_at    timestamp
);

-- Optional (recommended): only one "current" row per community+dimension
-- Remove if you want to allow duplicates.
CREATE UNIQUE INDEX ux_dimension_score_comm_dim
  ON dimension_score(community_id, dimension);

-- =========================
-- 7) COMMUNITY_COMPARISON (compare result persisted in one table)
-- =========================
CREATE TABLE community_comparison (
  comparison_id        varchar(64) PRIMARY KEY,

  community_a_id       varchar(64) NOT NULL,
  community_b_id       varchar(64) NOT NULL,

  created_at           timestamp,
  updated_at           timestamp,

  request_params_json  text,
  weights_used_json    text,

  structured_diff_json text,
  short_summary        text,
  tradeoffs_json       text,

  status               varchar(16),  -- ready|missing_data|error
  missing_fields_json  text,

  data_origin          varchar(16)   -- api|ai|mixed
);

-- Optional (recommended): avoid duplicates for A/B vs B/A if you normalize ordering in backend
CREATE UNIQUE INDEX ux_comparison_pair
  ON community_comparison(community_a_id, community_b_id);

-- Helpful indexes for query speed (optional)
CREATE INDEX ix_context_by_comm_type
  ON community_context(community_id, context_type);

CREATE INDEX ix_review_post_by_comm_time
  ON review_post(community_id, posted_at);

CREATE INDEX ix_review_signal_by_post
  ON review_signal(post_id);

CREATE INDEX ix_score_by_comm
  ON dimension_score(community_id);

CREATE INDEX ix_comparison_by_comm_a
  ON community_comparison(community_a_id);

CREATE INDEX ix_comparison_by_comm_b
  ON community_comparison(community_b_id);

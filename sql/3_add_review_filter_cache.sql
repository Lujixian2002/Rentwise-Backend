ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_keep boolean;
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_category varchar(32);
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_reason text;
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_model varchar(64);
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_prompt_version varchar(32);
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_text_hash varchar(64);
ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_checked_at timestamp;

CREATE INDEX IF NOT EXISTS ix_review_post_ai_filter_hash
  ON review_post(ai_filter_text_hash, ai_filter_model, ai_filter_prompt_version);

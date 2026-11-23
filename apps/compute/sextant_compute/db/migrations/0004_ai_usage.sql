-- AI Explain (ticket #39): one row per AI call, for the daily quota and the
-- per-user usage log (count and tokens).
--
-- User-owned per docs/adr/0001: user_id cascades from users, so deleting an
-- account removes its AI records. A row is inserted before the model is called
-- (it reserves one unit of the day's quota) and gets its token counts when the
-- model answers; a failed call deletes its row, so it is not charged.

CREATE TABLE ai_usage (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    tool          text NOT NULL,
    input_tokens  integer CHECK (input_tokens >= 0),
    output_tokens integer CHECK (output_tokens >= 0),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ai_usage_user_id_idx ON ai_usage (user_id, created_at);

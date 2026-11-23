-- Issue #54: keep the tokens of AI calls that fail. A failed call used to delete
-- its row, so tokens spent before the failure (e.g. several paid AI Analyst tool
-- rounds) never reached the operator view.
--
-- Now a failed call keeps its row with status 'failed' and the tokens it spent.
-- The daily quota counts only rows that are not 'failed', so the user-facing rule
-- stands: a failed call does not count against the user's quota. A reserved row
-- is 'ok' while the model is answering (it holds one unit of the quota).

ALTER TABLE ai_usage
    ADD COLUMN status text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'failed'));

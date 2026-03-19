-- Drop old 2-param overloads of scoring/extraction functions.
-- The parameterized versions (from 20260318) are the only ones the
-- Python code calls, and having both overloads makes PostgREST fail
-- with "could not choose a best candidate function" ambiguity errors.

DROP FUNCTION IF EXISTS score_domain_items(UUID, TIMESTAMPTZ);
DROP FUNCTION IF EXISTS extract_briefing_data(UUID, TIMESTAMPTZ);

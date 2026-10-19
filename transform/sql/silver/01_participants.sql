-- One row per participant, typed.
SELECT
  participant_id,
  CAST(classification_level AS INT)     AS classification_level,
  region,
  CAST(funding_start_date AS DATE)      AS funding_start_date,
  CAST(quarterly_budget_aud AS DOUBLE)  AS quarterly_budget_aud
FROM bronze_participants
WHERE participant_id IS NOT NULL

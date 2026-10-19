-- Per-worker punctuality over the whole period. Flags workers who need a conversation, not blame:
-- consistently late often means an impossible roster (travel time), which the region view helps check.
WITH w AS (
  SELECT
    v.worker_id, wk.region AS home_region, wk.employment_type,
    COUNT(*) AS scheduled_visits,
    SUM(CASE WHEN v.status = 'late'   THEN 1 ELSE 0 END) AS late_visits,
    SUM(CASE WHEN v.status = 'missed' THEN 1 ELSE 0 END) AS missed_visits,
    SUM(CASE WHEN v.missing_check_out THEN 1 ELSE 0 END) AS missing_check_outs,
    ROUND(AVG(CASE WHEN v.status = 'late' THEN v.late_minutes END), 1) AS avg_late_minutes,
    COUNT(DISTINCT v.participant_id) AS participants_served
  FROM silver_visits v
  LEFT JOIN silver_workers wk ON wk.worker_id = v.worker_id
  WHERE v.status <> 'future'
  GROUP BY v.worker_id, wk.region, wk.employment_type
)
SELECT
  *,
  ROUND(late_visits   / CAST(scheduled_visits AS DOUBLE), 3) AS late_rate,
  ROUND(missed_visits / CAST(scheduled_visits AS DOUBLE), 3) AS missed_rate,
  scheduled_visits >= 30 AND late_visits / CAST(scheduled_visits AS DOUBLE) > 0.2 AS needs_review
FROM w

-- Budget position per participant per quarter.
-- forecast = spend so far + in-house visits already booked for the rest of the quarter
--            + provider invoices at their current run rate.
WITH q AS (
  SELECT quarter_start, CAST(DATE_ADD(ADD_MONTHS(quarter_start, 3), -1) AS DATE) AS quarter_end
  FROM (SELECT DISTINCT CAST(DATE_TRUNC('QUARTER', service_date) AS DATE) AS quarter_start FROM silver_bookings) x
  WHERE quarter_start <= CAST('{{AS_OF_DATE}}' AS DATE)
),
spend AS (
  SELECT participant_id, CAST(DATE_TRUNC('QUARTER', service_date) AS DATE) AS quarter_start,
         SUM(CASE WHEN source = 'visit'   THEN amount_aud ELSE 0 END) AS visit_spend,
         SUM(CASE WHEN source = 'invoice' THEN amount_aud ELSE 0 END) AS invoice_spend
  FROM silver_spend
  GROUP BY participant_id, CAST(DATE_TRUNC('QUARTER', service_date) AS DATE)
),
booked AS (
  SELECT participant_id, CAST(DATE_TRUNC('QUARTER', service_date) AS DATE) AS quarter_start,
         SUM(booked_cost_aud) AS booked_aud
  FROM silver_visits
  WHERE status = 'future'
  GROUP BY participant_id, CAST(DATE_TRUNC('QUARTER', service_date) AS DATE)
),
base AS (
  SELECT
    p.participant_id, p.classification_level, p.region,
    q.quarter_start, q.quarter_end,
    CONCAT(CAST(YEAR(q.quarter_start) AS STRING), '-Q', CAST(QUARTER(q.quarter_start) AS STRING)) AS quarter,
    q.quarter_end <= CAST('{{AS_OF_DATE}}' AS DATE) AS is_closed,
    p.quarterly_budget_aud AS budget_aud,
    COALESCE(s.visit_spend, 0)   AS visit_spend_aud,
    COALESCE(s.invoice_spend, 0) AS invoice_spend_aud,
    COALESCE(b.booked_aud, 0)    AS booked_aud,
    DATEDIFF(LEAST(q.quarter_end, CAST('{{AS_OF_DATE}}' AS DATE)), q.quarter_start) + 1 AS days_elapsed,
    DATEDIFF(q.quarter_end, q.quarter_start) + 1 AS days_in_quarter
  FROM silver_participants p
  CROSS JOIN q
  LEFT JOIN spend  s ON s.participant_id = p.participant_id AND s.quarter_start = q.quarter_start
  LEFT JOIN booked b ON b.participant_id = p.participant_id AND b.quarter_start = q.quarter_start
),
f AS (
  SELECT
    *,
    visit_spend_aud + invoice_spend_aud AS spend_to_date_aud,
    visit_spend_aud + invoice_spend_aud + booked_aud
      + invoice_spend_aud / days_elapsed * (days_in_quarter - days_elapsed) AS forecast_spend_aud
  FROM base
)
SELECT
  participant_id, classification_level, region, quarter, quarter_start, quarter_end, is_closed,
  ROUND(budget_aud, 2)          AS budget_aud,
  ROUND(spend_to_date_aud, 2)   AS spend_to_date_aud,
  ROUND(booked_aud, 2)          AS booked_aud,
  ROUND(forecast_spend_aud, 2)  AS forecast_spend_aud,
  ROUND(days_elapsed / CAST(days_in_quarter AS DOUBLE), 3) AS pct_quarter_elapsed,
  ROUND(spend_to_date_aud / budget_aud, 3)  AS pct_budget_spent,
  ROUND(forecast_spend_aud / budget_aud, 3) AS forecast_pct_of_budget,
  CASE
    WHEN forecast_spend_aud > budget_aud        THEN 'Over budget'
    WHEN forecast_spend_aud < 0.7 * budget_aud  THEN 'Under-used'
    ELSE 'On track'
  END AS budget_status,
  -- illustrative carry-over rule: unspent funds up to the greater of $1,000 or 10% of the quarterly budget
  CASE WHEN forecast_spend_aud < budget_aud
       THEN ROUND(LEAST(budget_aud - forecast_spend_aud, GREATEST(1000.0, 0.1 * budget_aud)), 2)
       ELSE 0.0 END AS est_carry_over_aud,
  CASE WHEN forecast_spend_aud < budget_aud
       THEN ROUND(GREATEST(budget_aud - forecast_spend_aud - GREATEST(1000.0, 0.1 * budget_aud), 0.0), 2)
       ELSE 0.0 END AS est_funds_lost_aud
FROM f

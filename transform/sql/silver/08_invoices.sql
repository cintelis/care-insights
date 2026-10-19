-- Provider invoices, typed (providers send AU dd/MM/yyyy dates) and checked.
WITH i AS (
  SELECT
    invoice_number, provider_id, participant_id, service_code,
    TO_DATE(service_date, 'dd/MM/yyyy')  AS service_date,
    TO_DATE(received_date, 'dd/MM/yyyy') AS received_date,
    CAST(units AS DOUBLE)       AS units,
    CAST(unit_rate AS DOUBLE)   AS unit_rate,
    CAST(amount_aud AS DOUBLE)  AS amount_aud
  FROM bronze_invoices
),
ranked AS (
  SELECT
    i.*,
    ROW_NUMBER() OVER (
      PARTITION BY provider_id, participant_id, service_code, service_date, units, unit_rate
      ORDER BY received_date, invoice_number) AS copy_no
  FROM i
)
SELECT
  r.invoice_number, r.provider_id, r.participant_id, r.service_code, r.service_date, r.received_date,
  r.units, r.unit_rate, r.amount_aud, s.price_cap_aud,
  r.copy_no > 1                               AS is_duplicate,
  r.unit_rate > s.price_cap_aud + 0.005       AS is_over_cap,
  p.participant_id IS NULL                    AS is_unknown_participant,
  ABS(r.amount_aud - r.units * r.unit_rate) > 0.01 AS is_amount_mismatch,
  -- what we accept: nothing for duplicates/unknown participants; capped at the price cap otherwise
  CASE
    WHEN r.copy_no > 1 OR p.participant_id IS NULL THEN 0.0
    ELSE r.units * LEAST(r.unit_rate, s.price_cap_aud)
  END AS accepted_amount_aud
FROM ranked r
LEFT JOIN silver_service_types s ON s.service_code = r.service_code
LEFT JOIN silver_participants  p ON p.participant_id = r.participant_id

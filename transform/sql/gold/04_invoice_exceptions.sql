-- One row per invoice problem, with the money at stake.
WITH x AS (
  SELECT 'Duplicate invoice' AS exception_type, i.*, i.amount_aud AS amount_at_risk_aud
  FROM silver_invoices i WHERE is_duplicate
  UNION ALL
  SELECT 'Above price cap', i.*, ROUND(i.units * (i.unit_rate - i.price_cap_aud), 2)
  FROM silver_invoices i WHERE is_over_cap AND NOT is_duplicate
  UNION ALL
  SELECT 'Unknown participant', i.*, i.amount_aud
  FROM silver_invoices i WHERE is_unknown_participant AND NOT is_duplicate
  UNION ALL
  SELECT 'Amount does not match units x rate', i.*, ROUND(ABS(i.amount_aud - i.units * i.unit_rate), 2)
  FROM silver_invoices i WHERE is_amount_mismatch
)
SELECT
  x.exception_type, x.invoice_number, x.provider_id, pr.provider_name, x.participant_id,
  x.service_code, x.service_date, x.received_date, x.units, x.unit_rate, x.price_cap_aud,
  x.amount_aud, x.amount_at_risk_aud
FROM x
LEFT JOIN silver_providers pr ON pr.provider_id = x.provider_id

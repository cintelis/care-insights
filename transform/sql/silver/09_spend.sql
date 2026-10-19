-- Unified spend ledger: delivered in-house visits + accepted provider invoices.
SELECT participant_id, service_date, 'visit' AS source, service_code, cost_aud AS amount_aud
FROM silver_visits
WHERE status IN ('on_time', 'late')
UNION ALL
SELECT participant_id, service_date, 'invoice' AS source, service_code, accepted_amount_aud AS amount_aud
FROM silver_invoices
WHERE accepted_amount_aud > 0

-- Daily service delivery by region and service (actuals only).
SELECT
  v.service_date, v.region, v.service_code, s.service_name,
  COUNT(*)                                                    AS scheduled_visits,
  SUM(CASE WHEN v.status IN ('on_time', 'late') THEN 1 ELSE 0 END) AS delivered_visits,
  SUM(CASE WHEN v.status = 'on_time' THEN 1 ELSE 0 END)       AS on_time_visits,
  SUM(CASE WHEN v.status = 'late'    THEN 1 ELSE 0 END)       AS late_visits,
  SUM(CASE WHEN v.status = 'missed'  THEN 1 ELSE 0 END)       AS missed_visits,
  SUM(CASE WHEN v.missing_check_out  THEN 1 ELSE 0 END)       AS missing_check_outs,
  ROUND(AVG(CASE WHEN v.status = 'late' THEN v.late_minutes END), 1) AS avg_late_minutes,
  ROUND(SUM(v.cost_aud), 2)                                   AS delivered_value_aud
FROM silver_visits v
LEFT JOIN silver_service_types s ON s.service_code = v.service_code
WHERE v.status <> 'future'
GROUP BY v.service_date, v.region, v.service_code, s.service_name

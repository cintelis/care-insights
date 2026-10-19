-- One row per booking with what actually happened.
-- status: future | missed | late | on_time     (late = checked in more than 15 min after start)
WITH ev AS (
  SELECT
    booking_id,
    MIN(CASE WHEN event_type = 'check_in'  THEN event_ts END) AS check_in_ts,
    MAX(CASE WHEN event_type = 'check_out' THEN event_ts END) AS check_out_ts,
    MIN(CASE WHEN gps_verified THEN 1 ELSE 0 END)             AS all_gps_verified
  FROM silver_visit_events
  GROUP BY booking_id
),
v AS (
  SELECT
    b.booking_id, b.participant_id, b.worker_id, b.service_code, b.service_date,
    b.scheduled_start, b.scheduled_minutes, p.region,
    ev.check_in_ts, ev.check_out_ts,
    ROUND(TIMESTAMPDIFF(SECOND, b.scheduled_start, ev.check_in_ts) / 60.0, 1) AS late_minutes,
    ROUND(TIMESTAMPDIFF(SECOND, ev.check_in_ts, ev.check_out_ts) / 60.0, 1) AS actual_minutes,
    ev.all_gps_verified,
    s.price_cap_aud
  FROM silver_bookings b
  LEFT JOIN ev                    ON ev.booking_id = b.booking_id
  LEFT JOIN silver_participants p ON p.participant_id = b.participant_id
  LEFT JOIN silver_service_types s ON s.service_code = b.service_code
)
SELECT
  *,
  CASE
    WHEN service_date > CAST('{{AS_OF_DATE}}' AS DATE) THEN 'future'
    WHEN check_in_ts IS NULL                          THEN 'missed'
    WHEN late_minutes > 15                            THEN 'late'
    ELSE 'on_time'
  END AS status,
  check_in_ts IS NOT NULL AND check_out_ts IS NULL AS missing_check_out,
  -- billed on actual time; scheduled time when the check-out is missing; nothing when missed
  CASE
    WHEN service_date > CAST('{{AS_OF_DATE}}' AS DATE) THEN 0.0
    WHEN check_in_ts IS NULL THEN 0.0
    WHEN check_out_ts IS NULL THEN scheduled_minutes / 60.0 * price_cap_aud
    ELSE actual_minutes / 60.0 * price_cap_aud
  END AS cost_aud,
  -- what a future booking is expected to cost, for forecasting
  CASE WHEN service_date > CAST('{{AS_OF_DATE}}' AS DATE)
       THEN scheduled_minutes / 60.0 * price_cap_aud ELSE 0.0 END AS booked_cost_aud
FROM v

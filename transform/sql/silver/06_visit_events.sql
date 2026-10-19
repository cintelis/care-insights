-- Mobile app retries can send the same event twice: keep one per event_id.
SELECT event_id, booking_id, worker_id, event_type, event_ts, gps_verified
FROM (
  SELECT
    event_id, booking_id, worker_id, event_type,
    CAST(event_ts AS TIMESTAMP)    AS event_ts,
    CAST(gps_verified AS BOOLEAN)  AS gps_verified,
    ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_ts) AS rn
  FROM bronze_visit_events
) e
WHERE rn = 1

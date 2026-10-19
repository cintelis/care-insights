-- Latest version of each booking (the rostering system can resend rows).
SELECT booking_id, participant_id, worker_id, service_code, scheduled_start, scheduled_minutes,
       CAST(scheduled_start AS DATE) AS service_date
FROM (
  SELECT
    booking_id, participant_id, worker_id, service_code,
    CAST(scheduled_start AS TIMESTAMP)  AS scheduled_start,
    CAST(scheduled_minutes AS INT)      AS scheduled_minutes,
    ROW_NUMBER() OVER (PARTITION BY booking_id ORDER BY CAST(created_at AS TIMESTAMP) DESC) AS rn
  FROM bronze_bookings
) b
WHERE rn = 1

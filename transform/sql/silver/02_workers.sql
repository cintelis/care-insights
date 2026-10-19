SELECT worker_id, region, employment_type, CAST(start_date AS DATE) AS start_date
FROM bronze_workers

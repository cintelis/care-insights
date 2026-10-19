SELECT service_code, service_name, category, delivered_by, unit,
       CAST(price_cap_aud AS DOUBLE) AS price_cap_aud
FROM bronze_service_types

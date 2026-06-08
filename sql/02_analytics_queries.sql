-- Advanced SQL examples for the portfolio write-up and interview discussion.
-- These queries assume sql/01_schema.sql and sql/03_dashboard_views.sql have run.

-- 1) Daily charger utilization with LAG and rolling 7-day trend.
WITH daily AS (
    SELECT
        site_id,
        metric_date,
        session_count,
        total_kwh,
        utilization_rate,
        rolling_7d_utilization
    FROM mv_daily_site_metrics
),
trend AS (
    SELECT
        daily.*,
        LAG(utilization_rate) OVER (
            PARTITION BY site_id
            ORDER BY metric_date
        ) AS prior_day_utilization,
        utilization_rate
            - LAG(utilization_rate) OVER (
                PARTITION BY site_id
                ORDER BY metric_date
            ) AS utilization_delta
    FROM daily
)
SELECT *
FROM trend
ORDER BY site_id, metric_date;

-- 2) Peak load detection by month with ROW_NUMBER.
WITH monthly_peaks AS (
    SELECT
        site_id,
        date_trunc('month', hour_bucket_local)::DATE AS month_start,
        hour_bucket_local,
        estimated_avg_kw,
        active_sessions,
        ROW_NUMBER() OVER (
            PARTITION BY site_id, date_trunc('month', hour_bucket_local)
            ORDER BY estimated_avg_kw DESC, active_sessions DESC
        ) AS peak_rank
    FROM mv_hourly_site_load
)
SELECT
    site_id,
    month_start,
    hour_bucket_local AS peak_hour_local,
    estimated_avg_kw AS peak_kw,
    active_sessions
FROM monthly_peaks
WHERE peak_rank <= 5
ORDER BY site_id, month_start, peak_rank;

-- 3) Energy heatmap table by local weekday and hour.
WITH heatmap AS (
    SELECT
        site_id,
        local_isodow,
        local_hour,
        SUM(estimated_kwh) AS total_kwh,
        AVG(estimated_avg_kw) AS avg_kw,
        COUNT(*) AS observed_hours
    FROM mv_hourly_site_load
    GROUP BY site_id, local_isodow, local_hour
)
SELECT
    site_id,
    CASE local_isodow
        WHEN 1 THEN 'Mon'
        WHEN 2 THEN 'Tue'
        WHEN 3 THEN 'Wed'
        WHEN 4 THEN 'Thu'
        WHEN 5 THEN 'Fri'
        WHEN 6 THEN 'Sat'
        WHEN 7 THEN 'Sun'
    END AS day_name,
    local_hour,
    total_kwh,
    avg_kw,
    observed_hours
FROM heatmap
ORDER BY site_id, local_isodow, local_hour;

-- 4) Station-level anomaly detection using z-scores and rolling baselines.
WITH station_daily AS (
    SELECT
        station_id,
        site_id,
        connection_date AS metric_date,
        COUNT(*) AS sessions,
        SUM(kwh_delivered) AS total_kwh,
        AVG(session_duration_min) AS avg_duration_min
    FROM fact_charging_session
    GROUP BY station_id, site_id, connection_date
),
scored AS (
    SELECT
        station_daily.*,
        AVG(total_kwh) OVER (
            PARTITION BY station_id
            ORDER BY metric_date
            ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
        ) AS rolling_14d_kwh_avg,
        STDDEV_POP(total_kwh) OVER (
            PARTITION BY station_id
            ORDER BY metric_date
            ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
        ) AS rolling_14d_kwh_std
    FROM station_daily
)
SELECT
    *,
    (total_kwh - rolling_14d_kwh_avg) / NULLIF(rolling_14d_kwh_std, 0) AS z_score,
    CASE
        WHEN ABS((total_kwh - rolling_14d_kwh_avg) / NULLIF(rolling_14d_kwh_std, 0)) >= 3
            THEN 'Investigate station anomaly'
        ELSE 'Normal'
    END AS anomaly_flag
FROM scored
WHERE rolling_14d_kwh_avg IS NOT NULL
ORDER BY ABS((total_kwh - rolling_14d_kwh_avg) / NULLIF(rolling_14d_kwh_std, 0)) DESC NULLS LAST;

-- 5) Weekday vs weekend load-shape comparison.
WITH profile AS (
    SELECT
        site_id,
        CASE WHEN local_isodow IN (6, 7) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
        local_hour,
        AVG(estimated_avg_kw) AS avg_kw,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY estimated_avg_kw) AS p95_kw
    FROM mv_hourly_site_load
    GROUP BY site_id, day_type, local_hour
)
SELECT
    site_id,
    local_hour,
    MAX(avg_kw) FILTER (WHERE day_type = 'Weekday') AS weekday_avg_kw,
    MAX(avg_kw) FILTER (WHERE day_type = 'Weekend') AS weekend_avg_kw,
    MAX(p95_kw) FILTER (WHERE day_type = 'Weekday') AS weekday_p95_kw,
    MAX(p95_kw) FILTER (WHERE day_type = 'Weekend') AS weekend_p95_kw
FROM profile
GROUP BY site_id, local_hour
ORDER BY site_id, local_hour;

-- 6) Smart-charging and storage savings estimate.
WITH monthly_shift AS (
    SELECT
        site_id,
        date_trunc('month', connection_time)::DATE AS month_start,
        SUM(shiftable_kwh) AS shiftable_kwh,
        SUM(estimated_energy_cost_savings_usd) AS energy_arbitrage_savings_usd,
        COUNT(*) FILTER (WHERE shiftable_kwh > 0) AS flexible_sessions
    FROM mv_smart_charging_opportunities
    GROUP BY site_id, date_trunc('month', connection_time)
),
monthly_peak AS (
    SELECT
        site_id,
        date_trunc('month', hour_bucket_local)::DATE AS month_start,
        MAX(estimated_avg_kw) AS unmanaged_peak_kw,
        MAX(GREATEST(estimated_avg_kw - 250, 0)) AS storage_dispatch_limited_kw
    FROM mv_hourly_site_load
    GROUP BY site_id, date_trunc('month', hour_bucket_local)
)
SELECT
    s.site_id,
    s.month_start,
    s.shiftable_kwh,
    s.flexible_sessions,
    s.energy_arbitrage_savings_usd,
    p.unmanaged_peak_kw,
    p.storage_dispatch_limited_kw,
    p.storage_dispatch_limited_kw * 20.00 AS estimated_demand_charge_savings_usd,
    s.energy_arbitrage_savings_usd + p.storage_dispatch_limited_kw * 20.00
        AS total_estimated_savings_usd
FROM monthly_shift s
JOIN monthly_peak p
    ON p.site_id = s.site_id
   AND p.month_start = s.month_start
ORDER BY s.site_id, s.month_start;

-- 7) Station utilization quartiles for charger expansion planning.
WITH station_daily AS (
    SELECT
        station_id,
        site_id,
        connection_date,
        SUM(session_duration_min) / 60.0 AS occupied_hours,
        SUM(kwh_delivered) AS total_kwh
    FROM fact_charging_session
    GROUP BY station_id, site_id, connection_date
),
station_summary AS (
    SELECT
        station_id,
        site_id,
        AVG(occupied_hours / 24.0) AS avg_daily_utilization,
        AVG(total_kwh) AS avg_daily_kwh,
        COUNT(*) AS active_days
    FROM station_daily
    GROUP BY station_id, site_id
)
SELECT
    *,
    NTILE(4) OVER (
        PARTITION BY site_id
        ORDER BY avg_daily_utilization DESC
    ) AS utilization_quartile
FROM station_summary
ORDER BY site_id, utilization_quartile, avg_daily_utilization DESC;

-- 8) Driver request fulfillment using latest user input fields.
WITH claimed_sessions AS (
    SELECT
        user_id_hash,
        session_id,
        site_id,
        connection_time,
        kwh_delivered,
        kwh_requested,
        energy_request_gap_kwh,
        ROW_NUMBER() OVER (
            PARTITION BY user_id_hash
            ORDER BY connection_time
        ) AS user_session_number
    FROM fact_charging_session
    WHERE user_id_hash IS NOT NULL
      AND kwh_requested IS NOT NULL
),
user_rollup AS (
    SELECT
        user_id_hash,
        COUNT(*) AS claimed_sessions,
        AVG(kwh_delivered / NULLIF(kwh_requested, 0)) AS avg_fulfillment_ratio,
        AVG(energy_request_gap_kwh) AS avg_request_gap_kwh,
        MAX(user_session_number) AS latest_session_number
    FROM claimed_sessions
    GROUP BY user_id_hash
)
SELECT *
FROM user_rollup
WHERE claimed_sessions >= 5
ORDER BY avg_fulfillment_ratio ASC NULLS LAST;


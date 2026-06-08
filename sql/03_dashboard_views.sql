-- Rebuild dashboard materialized views after loading fact_charging_session.

DROP MATERIALIZED VIEW IF EXISTS mv_smart_charging_opportunities;
DROP MATERIALIZED VIEW IF EXISTS mv_daily_site_metrics;
DROP MATERIALIZED VIEW IF EXISTS mv_hourly_site_load;
DROP MATERIALIZED VIEW IF EXISTS mv_session_hourly_energy;

CREATE MATERIALIZED VIEW mv_session_hourly_energy AS
WITH expanded AS (
    SELECT
        f.session_id,
        f.site_id,
        f.station_id,
        gs.hour_bucket,
        gs.hour_bucket AT TIME ZONE COALESCE(s.timezone, f.timezone) AS hour_bucket_local,
        EXTRACT(
            EPOCH FROM LEAST(f.disconnect_time, gs.hour_bucket + INTERVAL '1 hour')
                 - GREATEST(f.connection_time, gs.hour_bucket)
        ) / 3600.0 AS overlap_hours,
        COALESCE(
            f.avg_power_kw,
            f.kwh_delivered / NULLIF(f.session_duration_min / 60.0, 0)
        ) AS estimated_kw
    FROM fact_charging_session f
    JOIN dim_site s
        ON s.site_id = f.site_id
    JOIN LATERAL generate_series(
        date_trunc('hour', f.connection_time),
        date_trunc('hour', f.disconnect_time),
        INTERVAL '1 hour'
    ) AS gs(hour_bucket)
        ON TRUE
    WHERE f.quality_flag = 'valid'
)
SELECT
    session_id,
    site_id,
    station_id,
    hour_bucket,
    hour_bucket_local,
    EXTRACT(ISODOW FROM hour_bucket_local)::INT AS local_isodow,
    EXTRACT(DOW FROM hour_bucket_local)::INT AS local_dow,
    EXTRACT(HOUR FROM hour_bucket_local)::INT AS local_hour,
    overlap_hours,
    estimated_kw,
    overlap_hours * estimated_kw AS estimated_kwh
FROM expanded
WHERE overlap_hours > 0;

CREATE INDEX idx_mv_session_hourly_energy_hour
    ON mv_session_hourly_energy(site_id, hour_bucket);

CREATE INDEX idx_mv_session_hourly_energy_station
    ON mv_session_hourly_energy(station_id, hour_bucket);

CREATE MATERIALIZED VIEW mv_hourly_site_load AS
SELECT
    site_id,
    hour_bucket,
    hour_bucket_local,
    local_isodow,
    local_dow,
    local_hour,
    COUNT(DISTINCT session_id) AS active_sessions,
    COUNT(DISTINCT station_id) AS active_stations,
    SUM(estimated_kwh) AS estimated_kwh,
    SUM(estimated_kwh) AS estimated_avg_kw
FROM mv_session_hourly_energy
GROUP BY
    site_id,
    hour_bucket,
    hour_bucket_local,
    local_isodow,
    local_dow,
    local_hour;

CREATE INDEX idx_mv_hourly_site_load_site_hour
    ON mv_hourly_site_load(site_id, hour_bucket);

CREATE MATERIALIZED VIEW mv_daily_site_metrics AS
WITH daily_sessions AS (
    SELECT
        f.site_id,
        f.connection_date AS metric_date,
        COUNT(*) AS session_count,
        COUNT(DISTINCT f.station_id) AS stations_used,
        COUNT(DISTINCT f.user_id_hash) FILTER (WHERE f.user_id_hash IS NOT NULL) AS known_users,
        SUM(f.kwh_delivered) AS total_kwh,
        AVG(f.kwh_delivered) AS avg_session_kwh,
        AVG(f.session_duration_min) AS avg_duration_min,
        SUM(f.session_duration_min) / 60.0 AS occupied_hours,
        SUM(f.charging_duration_min) / 60.0 AS charging_hours,
        SUM(f.idle_duration_min) / 60.0 AS idle_hours
    FROM fact_charging_session f
    GROUP BY f.site_id, f.connection_date
),
capacity AS (
    SELECT
        site_id,
        GREATEST(evse_count, 1) * 24.0 AS daily_capacity_hours
    FROM dim_site
)
SELECT
    d.*,
    c.daily_capacity_hours,
    d.occupied_hours / NULLIF(c.daily_capacity_hours, 0) AS utilization_rate,
    d.charging_hours / NULLIF(d.occupied_hours, 0) AS active_charging_share,
    AVG(d.total_kwh) OVER (
        PARTITION BY d.site_id
        ORDER BY d.metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_kwh,
    AVG(d.occupied_hours / NULLIF(c.daily_capacity_hours, 0)) OVER (
        PARTITION BY d.site_id
        ORDER BY d.metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_utilization
FROM daily_sessions d
JOIN capacity c
    ON c.site_id = d.site_id;

CREATE INDEX idx_mv_daily_site_metrics_site_date
    ON mv_daily_site_metrics(site_id, metric_date);

CREATE MATERIALIZED VIEW mv_smart_charging_opportunities AS
WITH rate_assumptions AS (
    SELECT
        0.42::DOUBLE PRECISION AS peak_rate_per_kwh,
        0.18::DOUBLE PRECISION AS off_peak_rate_per_kwh,
        20.00::DOUBLE PRECISION AS demand_charge_per_kw_month,
        0.90::DOUBLE PRECISION AS battery_round_trip_efficiency
),
session_peak AS (
    SELECT
        h.session_id,
        SUM(CASE WHEN h.local_hour BETWEEN 16 AND 20 THEN h.estimated_kwh ELSE 0 END) AS peak_window_kwh,
        SUM(h.estimated_kwh) AS estimated_total_kwh
    FROM mv_session_hourly_energy h
    GROUP BY h.session_id
)
SELECT
    f.session_id,
    f.site_id,
    f.station_id,
    f.connection_time,
    f.disconnect_time,
    f.kwh_delivered,
    f.session_duration_min,
    f.charging_duration_min,
    f.idle_duration_min,
    COALESCE(sp.peak_window_kwh, 0) AS peak_window_kwh,
    CASE
        WHEN f.idle_duration_min >= 60
            THEN LEAST(f.kwh_delivered, COALESCE(sp.peak_window_kwh, 0))
        ELSE 0
    END AS shiftable_kwh,
    CASE
        WHEN f.idle_duration_min >= 60
            THEN LEAST(f.kwh_delivered, COALESCE(sp.peak_window_kwh, 0))
                 * (r.peak_rate_per_kwh - r.off_peak_rate_per_kwh)
                 * r.battery_round_trip_efficiency
        ELSE 0
    END AS estimated_energy_cost_savings_usd,
    CASE
        WHEN f.idle_duration_min >= 60 AND COALESCE(sp.peak_window_kwh, 0) > 0
            THEN 'Defer charging or cover peak with onsite storage'
        WHEN f.idle_duration_min < 60
            THEN 'Low flexibility session'
        ELSE 'No peak-window charging detected'
    END AS recommendation
FROM fact_charging_session f
LEFT JOIN session_peak sp
    ON sp.session_id = f.session_id
CROSS JOIN rate_assumptions r;

CREATE INDEX idx_mv_smart_charging_opportunities_site
    ON mv_smart_charging_opportunities(site_id, connection_time);

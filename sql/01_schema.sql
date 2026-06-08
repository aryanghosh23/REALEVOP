-- Core PostgreSQL schema for ACN-Data EV charging analytics.

CREATE TABLE IF NOT EXISTS raw_acn_sessions (
    raw_id BIGSERIAL PRIMARY KEY,
    source_site_id TEXT NOT NULL,
    session_id TEXT,
    payload JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_site (
    site_id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    evse_count INTEGER NOT NULL,
    first_session_at TIMESTAMPTZ,
    last_session_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_station (
    station_id TEXT NOT NULL,
    site_id TEXT NOT NULL REFERENCES dim_site(site_id),
    space_id TEXT,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    session_count INTEGER NOT NULL,
    total_kwh_delivered DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (site_id, station_id)
);

CREATE TABLE IF NOT EXISTS fact_charging_session (
    session_id TEXT PRIMARY KEY,
    acn_id TEXT,
    site_id TEXT NOT NULL REFERENCES dim_site(site_id),
    cluster_id TEXT,
    station_id TEXT NOT NULL,
    space_id TEXT,
    connection_time TIMESTAMPTZ NOT NULL,
    disconnect_time TIMESTAMPTZ NOT NULL,
    done_charging_time TIMESTAMPTZ,
    connection_time_local TIMESTAMP,
    disconnect_time_local TIMESTAMP,
    connection_date DATE,
    connection_hour SMALLINT,
    connection_dow SMALLINT,
    connection_month TEXT,
    is_weekend BOOLEAN,
    kwh_delivered DOUBLE PRECISION NOT NULL,
    session_duration_min DOUBLE PRECISION NOT NULL,
    charging_duration_min DOUBLE PRECISION,
    idle_duration_min DOUBLE PRECISION,
    avg_power_kw DOUBLE PRECISION,
    avg_charging_power_kw DOUBLE PRECISION,
    wh_per_mile DOUBLE PRECISION,
    kwh_requested DOUBLE PRECISION,
    miles_requested DOUBLE PRECISION,
    minutes_available DOUBLE PRECISION,
    requested_departure TIMESTAMPTZ,
    payment_required BOOLEAN,
    user_input_modified_at TIMESTAMPTZ,
    energy_request_gap_kwh DOUBLE PRECISION,
    user_id_hash TEXT,
    timezone TEXT NOT NULL,
    quality_flag TEXT NOT NULL DEFAULT 'valid',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (disconnect_time > connection_time),
    CHECK (kwh_delivered >= 0),
    CHECK (session_duration_min > 0),
    FOREIGN KEY (site_id, station_id) REFERENCES dim_station(site_id, station_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_acn_sessions_session_id
    ON raw_acn_sessions(session_id);

CREATE INDEX IF NOT EXISTS idx_raw_acn_sessions_payload_gin
    ON raw_acn_sessions USING GIN(payload);

CREATE INDEX IF NOT EXISTS idx_fact_session_site_time
    ON fact_charging_session(site_id, connection_time);

CREATE INDEX IF NOT EXISTS idx_fact_session_station_time
    ON fact_charging_session(station_id, connection_time);

CREATE INDEX IF NOT EXISTS idx_fact_session_local_day_hour
    ON fact_charging_session(connection_dow, connection_hour);

CREATE INDEX IF NOT EXISTS idx_fact_session_user_hash
    ON fact_charging_session(user_id_hash);

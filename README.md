# EV Charging Energy Consumption Analytics & Optimization Dashboard

Portfolio project for Tesla Energy data analyst internship applications. The project turns public EV charging sessions into a PostgreSQL analytics mart, advanced SQL analyses, and an interactive Streamlit dashboard focused on load profiles, charger utilization, smart charging, and storage dispatch opportunities.

## Step-by-step build plan

1. Define the business problem: quantify when workplace EV charging creates peaks, where chargers are under or over-utilized, and how smart charging plus storage can reduce energy and demand costs.
2. Acquire ACN-Data from Caltech using either the official API or JSON export. Use Pecan Street Dataport only as an optional residential solar, storage, and EV extension.
3. Extract raw charging sessions with Python and persist immutable JSON in `data/raw/`.
4. Transform sessions into analysis-ready facts: duration, charging time, idle time, local day/hour, request fulfillment, average power, station dimensions, and hashed user IDs.
5. Load raw JSON, dimensions, and facts into PostgreSQL with SQLAlchemy.
6. Build PostgreSQL materialized views that expand sessions into hourly load estimates, daily utilization metrics, and smart-charging opportunity estimates.
7. Write advanced SQL examples using CTEs, window functions, `ROW_NUMBER`, `LAG`, rolling averages, anomaly scoring, interval expansion, and weekday/weekend comparisons.
8. Create an interactive dashboard for energy heatmaps, charger utilization trends, demand curves, and Tesla Energy recommendations.
9. Add Airflow-style orchestration so the workflow can run on a schedule.
10. Export CSV marts for Tableau screenshots, GitHub documentation, and recruiter-friendly project review.

## Dataset links

Primary dataset:

- ACN-Data official portal: <https://ev.caltech.edu/dataset.html>
- API base: `https://ev.caltech.edu/api/v1/`
- Session endpoint: `https://ev.caltech.edu/api/v1/sessions/<site_id>`
- Session endpoint with time series: `https://ev.caltech.edu/api/v1/sessions/<site_id>/ts`
- Register for an API token: <https://ev.caltech.edu/register>
- Python client docs: <https://acnportal.readthedocs.io/en/latest/acndata/data_client.html>
- Static archival snapshot: <https://github.com/tongxin-li/ACN-Data-Static>

Optional extension dataset:

- Pecan Street Dataport overview: <https://www.pecanstreet.org/dataport/>
- Pecan Street access and pricing: <https://www.pecanstreet.org/access/>

Use ACN-Data for this repo because it is open, has 30,000+ workplace charging sessions at Caltech, and maps directly to EV charging load-management questions. Pecan Street is excellent for a phase-two extension that joins residential EV charging with rooftop solar and battery storage, but it usually requires Dataport access.

## Repository structure

```text
.
|-- config/
|   `-- pipeline.yaml
|-- dags/
|   `-- ev_charging_elt_dag.py
|-- dashboard/
|   `-- app.py
|-- data/
|   |-- raw/
|   |-- processed/
|   `-- exports/
|-- sql/
|   |-- 01_schema.sql
|   |-- 02_analytics_queries.sql
|   `-- 03_dashboard_views.sql
|-- scripts/
|   `-- run_streamlit.cmd
|-- src/
|   `-- ev_charging_analytics/
|       |-- config.py
|       |-- extract.py
|       |-- load.py
|       |-- pipeline.py
|       |-- quality.py
|       |-- sql_utils.py
|       `-- transform.py
|-- tests/
|   `-- test_transform.py
|-- docker-compose.yml
|-- pyproject.toml
|-- requirements-airflow.txt
|-- requirements.txt
`-- README.md
```

## Local setup

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -e .
copy .env.example .env
docker compose up -d
```

## Quick dashboard demo without Docker

If you only want to see the dashboard working first, generate deterministic demo exports and start Streamlit:

```powershell
scripts\create_demo_data.cmd
scripts\run_streamlit.cmd
```

Then open `http://localhost:8501`. These demo CSVs are synthetic and are only for local UI review. Replace them with ACN-Data exports by running the real pipeline when PostgreSQL is available.

## Real ACN dashboard without Docker

If PostgreSQL/Docker is not installed yet, you can still use a downloaded ACN JSON export for the dashboard:

```powershell
copy "C:\Users\aryan\Downloads\acndata_sessions (2).json" data\raw\acn_sessions_caltech.json
scripts\export_real_data.cmd
scripts\run_streamlit.cmd
```

This creates real-data CSVs in `data\exports/` for the Streamlit and Tableau views. Later, when Docker Desktop is available, run the PostgreSQL ELT path for the full database-backed version.

Edit `.env` with your ACN API token:

```env
DATABASE_URL=postgresql+psycopg2://ev_user:ev_password@localhost:5432/ev_charging
ACN_API_TOKEN=your_token_here
ACN_SITE=caltech
ACN_START=2019-01-01
ACN_END=2020-12-31
ACN_RAW_JSON=data/raw/acn_sessions_caltech.json
```

## Loading instructions

### Option A: Live ACN API extraction

```bash
python -m ev_charging_analytics.pipeline --site caltech --start 2019-01-01 --end 2020-12-31
```

The pipeline follows ACN pagination links, writes raw JSON to `data/raw/`, transforms the sessions, loads PostgreSQL, refreshes materialized views, and exports dashboard CSVs.

### Option B: Offline JSON export

1. Go to <https://ev.caltech.edu/dataset.html>.
2. Select site `Caltech`.
3. Pick your date range.
4. Download the JSON file.
5. Save it as `data/raw/acn_sessions_caltech.json`.

Then run:

```bash
scripts\run_pipeline.cmd --skip-extract --raw-json data/raw/acn_sessions_caltech.json
```

### Optional static snapshot

For reproducible offline experiments, clone the static ACN snapshot:

```bash
git clone https://github.com/tongxin-li/ACN-Data-Static external/ACN-Data-Static
```

The static repo is time-series heavy. This project is built around session-level JSON, but the same schema can be extended with a `fact_charging_timeseries` table.

## PostgreSQL model

Core tables:

- `raw_acn_sessions`: immutable JSONB landing table for lineage.
- `dim_site`: site name, timezone, station count, first and last observed sessions.
- `dim_station`: station-level usage summary.
- `fact_charging_session`: one row per session with engineered analytics fields.

Materialized views:

- `mv_session_hourly_energy`: expands each session across hourly buckets using interval overlap logic.
- `mv_hourly_site_load`: site-level hourly kWh, estimated kW, active sessions, and active stations.
- `mv_daily_site_metrics`: daily utilization, energy, session count, idle time, and rolling 7-day metrics.
- `mv_smart_charging_opportunities`: shiftable peak-window kWh and estimated cost savings.

## Analyses included

- Charging session duration, charging duration, idle time, average power, and energy delivered.
- Charger utilization rate by day and station.
- Peak demand hours and hourly load profiles.
- Day-of-week and time-of-day consumption patterns.
- Anomaly detection for unusual station-level daily energy.
- Weekday versus weekend demand curves.
- Smart-charging opportunity based on flexible idle windows.
- Battery storage dispatch estimates for Powerwall, Megapack, and Virtual Power Plant relevance.

## Advanced SQL examples

See `sql/02_analytics_queries.sql` for:

1. Daily utilization trends with `LAG` and rolling 7-day windows.
2. Peak load ranking by site-month with `ROW_NUMBER`.
3. Energy heatmap table by local weekday and hour.
4. Station anomaly detection using rolling averages and z-scores.
5. Weekday versus weekend load-shape comparison.
6. Smart-charging and storage savings estimate.
7. Station utilization quartiles for charger expansion planning.
8. Driver request fulfillment analysis from latest user inputs.

## Dashboard

Run Streamlit:

```bash
streamlit run dashboard/app.py
```

On Windows, after installing requirements into `.venv`, you can also run:

```powershell
scripts\run_streamlit.cmd
```

The script prints `http://localhost:8501` and keeps the terminal busy while the dashboard is running. Press `Ctrl+C` in that terminal to stop it.

Dashboard sections:

- KPI row: sessions, stations, energy, average duration, average idle time.
- Energy heatmap by local day and hour.
- Peak demand curve with average and p95 estimated kW.
- Charger utilization trend with 7-day rolling average.
- Smart-charging opportunity by month.
- Tesla Energy recommendation text for Powerwall, Megapack, and VPP use cases.

## Tableau option

After the pipeline runs, connect Tableau to the CSV files in `data/exports/`:

- `sessions.csv`
- `hourly_site_load.csv`
- `daily_site_metrics.csv`
- `smart_charging_opportunities.csv`

Recommended Tableau sheets:

- Heatmap: columns `local_hour`, rows `local_isodow`, color `SUM(estimated_kwh)`.
- Utilization trend: `metric_date` versus `utilization_rate`, with `rolling_7d_utilization`.
- Peak demand: `local_hour` versus `AVG(estimated_avg_kw)` and p95 calculation.
- Storage savings: `month_start` versus `SUM(shiftable_kwh)` and `SUM(savings_usd)`.

## Airflow orchestration

The sample DAG in `dags/ev_charging_elt_dag.py` defines:

1. `extract_sessions`
2. `transform_sessions`
3. `load_postgres`
4. `refresh_marts_and_exports`

Install the package and Airflow dependencies in your Airflow environment:

```bash
pip install -e .
pip install -r requirements-airflow.txt
```

Then set the same environment variables from `.env.example` in your Airflow runtime.

## Tesla Energy relevance

This project mirrors the analytics problems Tesla Energy teams face when EV charging, solar generation, storage, and grid constraints interact:

- Detects site-level peak demand that can be reduced with controlled charging.
- Quantifies idle windows where charging can be shifted without hurting driver departure needs.
- Estimates how storage can absorb or shave peak EV load.
- Produces operational metrics for charger placement, utilization, reliability, and expansion planning.
- Frames recommendations around Powerwall, Megapack, and Virtual Power Plant participation.

## Resume bullet points

- Built an end-to-end EV charging analytics pipeline using Python, Pandas, SQLAlchemy, and PostgreSQL to ingest ACN-Data sessions, engineer load-management features, and publish dashboard-ready marts.
- Developed advanced PostgreSQL analyses with CTEs, window functions, rolling 7-day averages, interval-based hourly load bucketing, anomaly detection, and utilization metrics across 30,000+ charging sessions.
- Designed an interactive Streamlit dashboard showing charging demand heatmaps, peak-load curves, charger utilization trends, and smart-charging savings estimates for Tesla Energy storage use cases.
- Modeled storage and smart-charging opportunities by estimating peak-window shiftable kWh, energy arbitrage savings, and demand-charge reduction potential for Powerwall, Megapack, and VPP scenarios.

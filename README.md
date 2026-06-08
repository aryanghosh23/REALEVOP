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

## Upload Your Own Dataset In The Dashboard

The Streamlit dashboard sidebar includes an upload control for ad hoc analysis. Supported upload types:

- ACN-style `.json` session exports.
- Session-level `.csv` files with start time, energy/kWh, and preferably end time or duration.

Common CSV column names are detected automatically, including `start_time`, `end_time`, `station_id`, `charge_point_id`, `total_kwh`, `energy_kwh`, `duration`, and similar variants. Uploaded files are analyzed in memory for the current browser session and do not overwrite `data/exports/`.

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



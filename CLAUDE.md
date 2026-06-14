# CLAUDE.md

## core behavior
- if you are not sure -> ask me
- in case have the plan for implement, if anything not in the plan -> do not do that
- if the plan need to be change or append -> ask me

## Project

SWAT water balance automation pipeline for Thailand river basins. Runs SWAT simulations, aggregates outputs, and imports results into the WaterF PostgreSQL DB.

Active basins: **Yom** (`mb_code = "08"`) and **Ping** (`mb_code = "06"`).

## STG vs PROD

| | STG machine | PROD machine |
|---|---|---|
| Scripts | `historical_data/` | `swat_forecast/` |
| Purpose | Historical data recheck | Live forecast |
| DB strategy | Insert-only, no delete | DELETE mb_code → insert fresh |
| Data | Ping + Yom 2022–2024 | Yom + Ping rolling week/month |

**Do not mix** — historical insert-only scripts must not run on PROD, and PROD delete+insert scripts must not run on STG.

## Repository Structure

```
swat_forecast/              # PROD — live forecast pipeline
  utils.py                  # Shared: logger, send_email_alert, helpers
  send_summary.py           # Read run_state.json → send ONE summary email per run
  check_db.py               # Test DB connection (make check-db)
  requirements.txt
  swat_rev688/              # SWAT executable (gitignored, from Drive)
  yom/                      # Yom basin (mb_code=08)
    week.py                 # Entry point: weekly pipeline
    month.py                # Entry point: monthly pipeline
    config.py               # Shared path config
    simulation.py           # Download from HII API, write SWAT inputs, run executable
    analysis.py             # Parse SWAT outputs → Results_staging/
    _db.py                  # Shared DB helpers (read_csv, copy_insert, run, date utils)
    import_basin_7days.py   # week/Results → basin_*_7days
    import_basin_6months.py # month/Results → basin_*_6months
    import_admin_7days.py   # week/Results → forecast_*_7days
    import_admin_6months.py # month/Results → forecast_*_6months
    import_basin_daily.py   # week+month/Results → basin_*_daily_7days + _6months
    import_admin_daily.py   # week+month/Results → forecast_*_daily_7days + _6months
    Inputs/                 # Static config/threshold files
    week/                   # Runtime dirs (gitignored)
      TxtInOut/             # SWAT model inputs (from Drive)
      Results/              # Final output CSVs
      Results_staging/      # Staging (renamed to Results on success)
      Logs/                 # run_state.json + timestamped import logs
      Alerts/
    month/                  # Same layout as week/
  ping/                     # Ping basin (mb_code=06) — same structure as yom/

historical_data/            # STG — 2022–2024 insert-only scripts
  _db.py
  import_basin_7days.py     # ping+yom → basin_*_7days (insert only)
  import_basin_6months.py
  import_admin_7days.py
  import_admin_6months.py
  import_basin_daily.py
  import_admin_daily.py
  clear_db.py               # Delete all rows for both basins
  clear_basin.py            # Delete rows for one basin: python3 clear_basin.py [ping|yom]
  verify_db.py              # Print row counts + date ranges per basin per table
  ping/                     # Historical CSVs 2022–2024 (gitignored, from Drive)
  yom/

swat_file_DB/               # Drive zip downloads (gitignored)
.env                        # Credentials + feature flags (gitignored)
.env.example                # Template with all keys
Makefile
setup.sh
```

## Pipeline Flow

Each pipeline is triggered via `make` and runs in sequence with `&&` (stops on any failure):

```
make run-week-yom:
  week.py
    ├── Phase 1: Download input CSVs from tiservice.hii.or.th (Rain, Temp, Rh, Wind, Solar)
    ├── Phase 2: Write SWAT input files to week/TxtInOut/
    ├── Phase 3: Run SWAT executable
    ├── Phase 4: Parse outputs → week/Results_staging/
    │     ├── Bonwr_Weekly.csv / Bonwr_Daily.csv        (basin/watershed)
    │     ├── Sbonwr_Weekly.csv / Sbonwr_Daily.csv      (subbasin L1)
    │     ├── Analysis_Sbswat_Weekly.csv                (subbasin L2)
    │     ├── Province_Weekly.csv / Province_Daily.csv  (admin: province)
    │     ├── Amphoe_Weekly.csv / Amphoe_Daily.csv      (admin: amphoe)
    │     └── Tambol_Weekly.csv / Tambol_Daily.csv      (admin: tambon)
    └── Phase 5: Rename Results_staging → Results (only on full success)
  import_basin_7days.py   → basin_*_7days tables
  import_admin_7days.py   → forecast_*_7days tables
  import_basin_daily.py   → basin_*_daily_7days + basin_*_daily_6months tables
  import_admin_daily.py   → forecast_*_daily_7days + forecast_*_daily_6months tables
  send_summary.py week yom → reads Logs/run_state.json → sends email

make run-month-yom: (same flow, *_Weekly → *_Monthly, 180-day window)
  month.py → import_basin_6months.py → import_admin_6months.py
           → import_basin_daily.py   → import_admin_daily.py
           → send_summary.py month yom
```

On failure: staging dir is discarded, Results is untouched, summary email is sent regardless.

Each import script appends a JSON entry to `Logs/run_state.json`. `send_summary.py` reads this file and sends one email covering simulation + all DB imports.

## DB Tables

All tables have `wb_level` (float) column. Schema lives in `/root/code/waterF/init-scripts/`. Run `make hard-reset` in waterF to recreate from scratch.

| CSV File(s) | DB Tables | PROD script | STG script |
|---|---|---|---|
| `Bonwr_Weekly.csv` | `basin_watershed_7days` | `import_basin_7days.py` | same (copied) |
| `Sbonwr_Weekly.csv` | `basin_subbasin_l1_7days` | `import_basin_7days.py` | same |
| `Analysis_Sbswat_Weekly.csv` | `basin_subbasin_l2_7days` | `import_basin_7days.py` | same |
| `Bonwr_Monthly.csv` | `basin_watershed_6months` | `import_basin_6months.py` | same |
| `Sbonwr_Monthly.csv` | `basin_subbasin_l1_6months` | `import_basin_6months.py` | same |
| `Analysis_Sbswat_Monthly.csv` | `basin_subbasin_l2_6months` | `import_basin_6months.py` | same |
| `Province_Weekly.csv` | `forecast_province_7days` | `import_admin_7days.py` | same |
| `Amphoe_Weekly.csv` | `forecast_amphoe_7days` | `import_admin_7days.py` | same |
| `Tambol_Weekly.csv` | `forecast_tambon_7days` | `import_admin_7days.py` | same |
| `Province_Monthly.csv` | `forecast_province_6months` | `import_admin_6months.py` | same |
| `Amphoe_Monthly.csv` | `forecast_amphoe_6months` | `import_admin_6months.py` | same |
| `Tambol_Monthly.csv` | `forecast_tambon_6months` | `import_admin_6months.py` | same |
| `Bonwr_Daily.csv` | `basin_watershed_daily_7days` + `_6months` | `import_basin_daily.py` | same |
| `Sbonwr_Daily.csv` | `basin_subbasin_l1_daily_7days` + `_6months` | `import_basin_daily.py` | same |
| `Analysis_Sbswat.csv` | `basin_subbasin_l2_daily_7days` + `_6months` | `import_basin_daily.py` | same |
| `Province_Daily.csv` | `forecast_province_daily_7days` + `_6months` | `import_admin_daily.py` | same |
| `Amphoe_Daily.csv` | `forecast_amphoe_daily_7days` + `_6months` | `import_admin_daily.py` | same |
| `Tambol_Daily.csv` | `forecast_tambon_daily_7days` + `_6months` | `import_admin_daily.py` | same |

**PROD**: each import does `DELETE WHERE mb_code = ANY(MB_CODES)` then bulk-inserts. Basins are independent — a Yom run never touches Ping rows.

**STG**: insert-only (no DELETE). Daily files go into both `_7days` and `_6months` tables from the same historical CSV.

## Environment (.env)

```
# SMTP (email alerts on failure)
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
ALERT_EMAIL=email1@example.com,email2@example.com

# DB (same credentials as waterF)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=...
DATABASE_NAME=postgres

# Data source
HII_BASE_URL=https://tiservice.hii.or.th/water_balance

# Feature flags
# Set to false to skip DB saving (useful for teammates without a local DB)
SWAT_SAVE_DB=true
```

`SWAT_SAVE_DB=false` — DB connection is skipped entirely for all import steps. Each step is recorded as `skipped: true` in `run_state.json` and appears as `SKIPPED (DB disabled)` in the summary email. Does NOT count as a failure.

## Make Commands

```bash
make setup             # First-time setup: venv + download from Drive + unpack
make check-db          # Test DB connection

# PROD
make run-week-yom      # Run Yom weekly pipeline + all DB imports + summary email
make run-month-yom     # Run Yom monthly pipeline + all DB imports + summary email
make run-week-ping     # Run Ping weekly pipeline + all DB imports + summary email
make run-month-ping    # Run Ping monthly pipeline + all DB imports + summary email
make run-all-forecast  # Run all 4 pipelines (week always; month skipped if no data)
make full-run          # run-all-forecast then import-historical

# Re-import without re-running SWAT
make reimport-forecast # Re-import from existing Results/ (no SWAT run)
make reimport-all      # clear-db then reimport-forecast then import-historical

# Historical (STG)
make import-historical # Insert Ping + Yom historical data (insert only, no delete)
make clear-ping        # Delete all Ping (mb_code=06) rows from all tables
make clear-yom         # Delete all Yom (mb_code=08) rows from all tables
make clear-db          # Delete ALL rows for both basins from all 24 tables
make verify-db         # Print row counts + date ranges per basin in all tables

# Cron
make install-cron      # Install all pipeline cron jobs + log rotation (idempotent)
make uninstall-cron    # Remove this project's cron jobs only
make show-cron         # Show current crontab

# Drive / unpack
make download-drive    # Download all zips from Google Drive into swat_file_DB/
make unpack-all        # Unpack TxtInOut + swat_rev688 + historical
```

## First-Time Setup

```bash
# 1. Clone and configure
git clone https://github.com/robotayyyyy/waterBalanceScript
cd waterBalanceScript
cp .env.example .env
nano .env   # fill in DATABASE_HOST, DATABASE_PASSWORD, SMTP_PASS, ALERT_EMAIL

# 2. Run full setup (creates venvs, downloads from Drive, unpacks all zips)
bash setup.sh

# 3. Verify DB connection
make check-db

# 4. Install cron
make install-cron
```

## Cron

Managed via Makefile — `make install-cron` writes entries for all four pipelines plus monthly log cleanup. All four run daily so the pipeline fires whenever input data is available on the HII server.

```
0  1 * * *  make run-week-yom   >> swat_forecast/yom/week/Logs/cron.log
2  1 * * *  make run-week-ping  >> swat_forecast/ping/week/Logs/cron.log
5  1 * * *  make run-month-yom  >> swat_forecast/yom/month/Logs/cron.log
10 1 * * *  make run-month-ping >> swat_forecast/ping/month/Logs/cron.log
15 1 * * *  find swat_forecast/*/*/Logs -name '*.log' -mtime +90 -delete
```

## Adding a New Basin to PROD

1. Duplicate `swat_forecast/yom/` → `swat_forecast/{basin}/`, update `basin_id`, `mb_code`, `mb_name_t`, `total_subbasins` in `week.py` and `month.py`
2. Add `Inputs/` reference files for the basin
3. Add `run-week-{basin}` and `run-month-{basin}` targets to `Makefile`
4. Upload TxtInOut zips and historical zip to Google Drive; run `make download-drive unpack-all`
5. Add cron entries via `make install-cron`

# CLAUDE.md

## Project

SWAT water balance automation pipeline for Thailand river basins. Runs SWAT simulations, aggregates outputs, and imports results into the WaterF PostgreSQL DB.

Active basins: **Yom** (`mb_code = "08"`) and **Ping** (`mb_code = "06"`).

## STG vs PROD

| | STG machine | PROD machine |
|---|---|---|
| Scripts | `Analysis_Result/` | `swat/yom/` |
| Purpose | Historical data recheck | Live forecast |
| DB strategy | Insert-only, no delete | DELETE mb_code → insert fresh |
| Data | Ping + Yom 2022–2024 | Yom rolling week/month |

**Do not mix** — historical insert-only scripts must not run on PROD, and PROD delete+insert scripts must not run on STG.

## Repository Structure

```
Analysis_Result/             # STG only — historical results + import scripts
  ping/                      # Ping historical output CSVs (2022–2024)
  yom/                       # Yom historical output CSVs (2022–2024)
  _db.py                     # Copy of DB helpers
  import_basin_7days.py      # ping+yom → basin_*_7days (insert only)
  import_basin_6months.py    # ping+yom → basin_*_6months (insert only)
  import_admin_7days.py      # ping+yom → forecast_*_7days (insert only)
  import_admin_6months.py    # ping+yom → forecast_*_6months (insert only)
  import_basin_daily.py      # ping+yom → basin_*_daily_7days + 6months (insert only)
  import_admin_daily.py      # ping+yom → forecast_*_daily_7days + 6months (insert only)
  clear_basin.py             # Delete all rows for one basin: python3 clear_basin.py [ping|yom]
  verify_db.py               # Print row counts + date ranges per basin per table

swat/
  setup.sh                     # First-time setup: venv + install deps (auto-runs week.py at end)
  requirements.txt             # Python deps (pandas, numpy, python-dotenv, psycopg2-binary, requests)
  check_db.py                  # Test DB connection (used by make check-db)
  .env                         # SMTP + DB credentials (gitignored)
  .gitignore

  swat_rev688/
    rev688_64rel_linux         # SWAT executable (Linux 64-bit)

  yom_month_TxtInOut.tar.xz   # Yom monthly SWAT model inputs (not in git, copy to EC2 manually)
  yom_week_TxtInOut.tar.xz    # Yom weekly SWAT model inputs (not in git, copy to EC2 manually)

  yom/
    week.py                    # Entry point: weekly pipeline (SWAT_MODE=week)
    month.py                   # Entry point: monthly pipeline (SWAT_MODE=month)
    config.py                  # Shared path config (reads SWAT_MODE env var)
    simulation.py              # Download, write SWAT inputs, run executable
    analysis.py                # Parse SWAT outputs → Results_staging/
    utils.py                   # Logger, email alerts, helper functions

    _db.py                     # Shared DB helpers (read_csv, copy_insert, run, date utils)
    import_basin_6months.py    # month/Results → basin_*_6months + wb_level
    import_basin_7days.py      # week/Results  → basin_*_7days + wb_level
    import_admin_6months.py    # month/Results → forecast_*_6months + wb_level
    import_admin_7days.py      # week/Results  → forecast_*_7days + wb_level
    import_basin_daily.py      # week+month/Results → basin_*_daily_7days + basin_*_daily_6months
    import_admin_daily.py      # week+month/Results → forecast_*_daily_7days + forecast_*_daily_6months

    Inputs/                    # Static config/threshold files
      res_mapping.json
      wus.csv
      fraction.csv
      SBfraction.csv
      drought_thershold.csv
      runoff_thresholds.csv
      runoff/
        day/, week/, month/    # Per-period runoff critical thresholds (6 levels each)
      WB_level/
        day/, week/, month/    # Per-period water balance level thresholds (6 levels each)

    month/                     # Monthly working dirs
      TxtInOut/                # Unpacked from yom_month_TxtInOut.tar.xz
      Results/                 # Final output CSVs (replaced atomically on each successful run)
      Results_staging/         # Staging dir (renamed to Results on success)
      Logs/
      Alerts/

    week/                      # Weekly working dirs (same layout as month/)
      TxtInOut/
      Results/
      ...
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

make run-month-yom: (same flow, SWAT_MODE=month, *_Weekly → *_Monthly, 180-day window)
  month.py → import_basin_6months.py → import_admin_6months.py
           → import_basin_daily.py   → import_admin_daily.py
```

On failure: staging dir is discarded, Results is untouched, email alert is sent.

Note: `import_basin_daily.py` and `import_admin_daily.py` import daily data from **both** week and month Results in a single run — so running either make target keeps all daily tables current.

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
ALERT_RECEIVER_EMAIL=...

# DB (same credentials as waterF)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=...
DATABASE_NAME=postgres
```

## Make Commands

```bash
# PROD
make setup             # First-time setup: venv + install deps (runs week.py at end)
make check-db          # Test DB connection
make run-week-yom      # Run Yom weekly pipeline + all DB imports
make run-month-yom     # Run Yom monthly pipeline + all DB imports
make zip-txtinout-yom  # Repack TxtInOut dirs → *.tar.xz
make unpack-yom        # Unpack *.tar.xz into yom/month/ and yom/week/

# STG (historical)
make import-historical # Insert Ping + Yom historical data into all DB tables (no delete)
make clear-ping        # Delete all Ping (mb_code=06) rows from all tables (with confirmation)
make clear-yom         # Delete all Yom (mb_code=08) rows from all tables (with confirmation)
make verify-db         # Print row counts + date ranges per basin in all tables
```

## First-Time Setup (EC2)

```bash
# 1. Copy model archives (not in git)
scp swat/yom_month_TxtInOut.tar.xz swat/yom_week_TxtInOut.tar.xz ec2-user@<host>:/path/to/waterBalanceScript/swat/

# 2. Run setup (creates venv, installs deps, runs weekly pipeline)
cd /path/to/waterBalanceScript
make setup
```

## Cron (EC2)

```
# Weekly — every Monday 01:00
0 1 * * 1  cd /path/to/waterBalanceScript && make run-week-yom

# Monthly — 1st of each month 02:00
0 2 1 * *  cd /path/to/waterBalanceScript && make run-month-yom
```

## Adding Ping Basin to PROD Pipeline

Ping historical data (2022–2024) is already loaded on STG via `Analysis_Result/`. To add Ping to the live PROD forecast pipeline:

1. Create `swat/ping/week.py` and `swat/ping/month.py` (copy from `yom/`, change `mb_code` to `"06"`)
2. Uncomment the `"Ping"` line in all 6 PROD import scripts under `swat/yom/`:
   - `import_basin_6months.py`, `import_basin_7days.py`
   - `import_admin_6months.py`, `import_admin_7days.py`
   - `import_basin_daily.py`, `import_admin_daily.py`
3. Add Makefile targets `run-week-ping` and `run-month-ping`
4. Add cron entries

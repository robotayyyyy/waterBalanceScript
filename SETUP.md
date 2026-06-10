# Setup Guide

## Overview

This repo runs SWAT water balance simulations and imports results into the WaterF PostgreSQL database.

**Two machines are involved:**
- **Machine A** — runs waterF (web app + PostgreSQL via Docker)
- **Machine B** — runs this repo (SWAT analysis + DB import)

Both machines must be running and reachable from each other.

---

## Prerequisites

### Machine A — waterF DB must be running

```bash
cd /path/to/waterF
make hard-reset    # first time only — wipes DB and rebuilds schema from init-scripts/
# or
docker compose up -d   # if already set up
```

Verify the DB is up:
```bash
docker ps | grep postgres
```

### Machine A — allow Machine B to connect to PostgreSQL

PostgreSQL exposes port 5432 via Docker. Allow Machine B's IP:

```bash
# Find pg_hba.conf location
docker exec postgres_db psql -U postgres -c "SHOW hba_file;"

# Allow Machine B (replace <Machine-B-IP>)
docker exec postgres_db bash -c "echo 'host all all <Machine-B-IP>/32 md5' >> /var/lib/postgresql/data/pg_hba.conf"

# Reload config
docker exec postgres_db psql -U postgres -c "SELECT pg_reload_conf();"
```

Verify from Machine B that the port is reachable:
```bash
nc -zv <Machine-A-IP> 5432
```

---

## What to Prepare Before Deploying

These files are **not in git** and must be copied manually to EC2:

| File | Why not in git | How to get it |
|---|---|---|
| `swat/yom_month_TxtInOut.tar.xz` | Too large | Run `make zip-txtinout-yom` locally, then `scp` to EC2 |
| `swat/yom_week_TxtInOut.tar.xz` | Too large | Same as above |
| `swat/.env` | Contains secrets | Create manually on EC2 (see Step 4) |

The venv (`swat/env/`) is also not in git but is created automatically by `make setup`.

---

## Machine B — Setup waterBalanceScript

### Step 1 — check Python 3

```bash
python3 --version   # need 3.8+
```

If not found:
```bash
sudo apt-get update && sudo apt-get install python3 python3-venv python3-pip -y
```

### Step 2 — clone the repo

```bash
git clone <repo-url> /path/to/waterBalanceScript
cd /path/to/waterBalanceScript
```

### Step 3 — copy model archives (not in git)

The SWAT model input archives are too large for git. Copy them from whoever has them:

```bash
# Run on the machine that has the archives
scp swat/yom_month_TxtInOut.tar.xz  user@<Machine-B-IP>:/path/to/waterBalanceScript/swat/
scp swat/yom_week_TxtInOut.tar.xz   user@<Machine-B-IP>:/path/to/waterBalanceScript/swat/
```

To rebuild them from an existing setup:
```bash
make zip-txtinout-yom   # creates both .tar.xz files from current TxtInOut dirs
```

### Step 4 — create the .env file

```bash
nano /path/to/waterBalanceScript/swat/.env
```

Fill in:
```
# DB — point to Machine A
DATABASE_HOST=<Machine-A-IP>
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=<password>
DATABASE_NAME=postgres

# SMTP — email alerts on pipeline failure
SMTP_HOST=mailrelay.uc-workd.com
SMTP_PORT=587
SMTP_USER=noreply@hii.or.th
SMTP_PASS=<password>
ALERT_RECEIVER_EMAIL=your-email@example.com
```

### Step 5 — run setup

```bash
cd /path/to/waterBalanceScript
make setup
```

This will:
- Create Python venv at `swat/env/`
- Install all dependencies (`pandas`, `numpy`, `psycopg2`, `requests`, etc.)
- Fix SWAT executable permissions
- Automatically run the weekly pipeline as a smoke test

### Step 6 — verify DB connection

```bash
make check-db
```

Expected output: `✓ Connected to DB: {...}`

---

## Running the Pipelines

```bash
make run-week-yom    # weekly SWAT run + import to DB (run every Monday)
make run-month-yom   # monthly SWAT run + import to DB (run 1st of each month)
```

Each command runs the full pipeline:
1. Download input data from `tiservice.hii.or.th`
2. Run SWAT simulation
3. Parse outputs → Results/
4. Import all CSV results into DB

On failure: results are not committed to DB and an email alert is sent to `ALERT_RECEIVER_EMAIL`.

---

## Cron Setup (EC2)

```bash
crontab -e
```

Add:
```
# Weekly — every Monday 01:00
0 1 * * 1  cd /path/to/waterBalanceScript && make run-week-yom >> /var/log/swat-week.log 2>&1

# Monthly — 1st of each month 02:00
0 2 1 * *  cd /path/to/waterBalanceScript && make run-month-yom >> /var/log/swat-month.log 2>&1
```

---

## DB Schema (reference)

Schema is defined in `waterF/init-scripts/`. Run `make hard-reset` in waterF to recreate all tables. See `swat/yom/TABLES.md` for a full CSV → table mapping.

**24 tables total** (12 per model):

| Group | Tables |
|---|---|
| Weekly aggregated | `basin_watershed_7days`, `basin_subbasin_l1_7days`, `basin_subbasin_l2_7days`, `forecast_province_7days`, `forecast_amphoe_7days`, `forecast_tambon_7days` |
| Monthly aggregated | `basin_watershed_6months`, `basin_subbasin_l1_6months`, `basin_subbasin_l2_6months`, `forecast_province_6months`, `forecast_amphoe_6months`, `forecast_tambon_6months` |
| Weekly daily | `basin_watershed_daily_7days`, `basin_subbasin_l1_daily_7days`, `basin_subbasin_l2_daily_7days`, `forecast_province_daily_7days`, `forecast_amphoe_daily_7days`, `forecast_tambon_daily_7days` |
| Monthly daily | `basin_watershed_daily_6months`, `basin_subbasin_l1_daily_6months`, `basin_subbasin_l2_daily_6months`, `forecast_province_daily_6months`, `forecast_amphoe_daily_6months`, `forecast_tambon_daily_6months` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | venv not activated — use `make` commands, not `python3` directly |
| `Connection refused` on DB | Check Machine A's Docker is running and pg_hba.conf allows Machine B's IP |
| `make check-db` fails | Wrong credentials in `swat/.env` |
| SWAT executable permission denied | Run `make setup` again to restore permissions |
| Download timeout | `tiservice.hii.or.th` is unreachable — check network/firewall on Machine B |

.DEFAULT_GOAL := help
.PHONY: help setup check-db \
        run-month-yom run-week-yom run-month-ping run-week-ping run-all-forecast \
        reimport-forecast reimport-all clear-db \
        download-drive unpack-yom unpack-ping unpack-swat unpack-historical unpack-all print-swat-dir \
        import-historical clear-ping clear-yom verify-db \
        full-run

ROOT_DIR  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
SWAT_DIR  := $(ROOT_DIR)/swat
FORE_DIR  := $(ROOT_DIR)/swat_forecast
HIST_DIR  := $(ROOT_DIR)/historical_data
FILE_DB   := $(ROOT_DIR)/swat_file_DB
DRIVE_URL := https://drive.google.com/drive/folders/1fCaorGy1KrrjTyVYX00a8CO88SsqChTm
PYTHON    = $(SWAT_DIR)/env/bin/python3
PYTHON_F  = $(FORE_DIR)/env/bin/python3
PYTHON_H  = $(HIST_DIR)/env/bin/python3

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  %-22s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## First-time setup: venv + download from Drive + unpack
	bash $(ROOT_DIR)/setup.sh

check-db: ## Test DB connection
	cd $(SWAT_DIR) && $(PYTHON) check_db.py

# ── Forecast (live) — DELETE+INSERT per basin ────────────────────────────────

run-week-yom: ## Forecast: run Yom weekly SWAT + import to DB
	cd $(FORE_DIR)/yom && $(PYTHON_F) week.py
	cd $(FORE_DIR) && $(PYTHON_F) yom/import_basin_7days.py \
		&& $(PYTHON_F) yom/import_admin_7days.py \
		&& $(PYTHON_F) yom/import_basin_daily.py \
		&& $(PYTHON_F) yom/import_admin_daily.py

run-month-yom: ## Forecast: run Yom monthly SWAT + import to DB (skips imports if SWAT fails)
	cd $(FORE_DIR)/yom && $(PYTHON_F) month.py \
		&& cd $(FORE_DIR) && $(PYTHON_F) yom/import_basin_6months.py \
		&& $(PYTHON_F) yom/import_admin_6months.py \
		&& $(PYTHON_F) yom/import_basin_daily.py \
		&& $(PYTHON_F) yom/import_admin_daily.py

run-week-ping: ## Forecast: run Ping weekly SWAT + import to DB
	cd $(FORE_DIR)/ping && $(PYTHON_F) week.py
	cd $(FORE_DIR) && $(PYTHON_F) ping/import_basin_7days.py \
		&& $(PYTHON_F) ping/import_admin_7days.py \
		&& $(PYTHON_F) ping/import_basin_daily.py \
		&& $(PYTHON_F) ping/import_admin_daily.py

run-month-ping: ## Forecast: run Ping monthly SWAT + import to DB (skips imports if SWAT fails)
	cd $(FORE_DIR)/ping && $(PYTHON_F) month.py \
		&& cd $(FORE_DIR) && $(PYTHON_F) ping/import_basin_6months.py \
		&& $(PYTHON_F) ping/import_admin_6months.py \
		&& $(PYTHON_F) ping/import_basin_daily.py \
		&& $(PYTHON_F) ping/import_admin_daily.py

run-all-forecast: run-week-yom run-week-ping ## Forecast: run ALL (weeks always run; months skipped if data unavailable)
	-$(MAKE) run-month-yom
	-$(MAKE) run-month-ping

# ── Forecast import only — no SWAT re-run, reuses existing Results/ ──────────

reimport-forecast: ## Re-import forecast for all basins from existing Results (no SWAT run)
	cd $(FORE_DIR) && $(PYTHON_F) yom/import_basin_7days.py \
		&& $(PYTHON_F) yom/import_admin_7days.py \
		&& $(PYTHON_F) yom/import_basin_daily.py \
		&& $(PYTHON_F) yom/import_admin_daily.py \
		&& $(PYTHON_F) yom/import_basin_6months.py \
		&& $(PYTHON_F) yom/import_admin_6months.py \
		&& $(PYTHON_F) ping/import_basin_7days.py \
		&& $(PYTHON_F) ping/import_admin_7days.py \
		&& $(PYTHON_F) ping/import_basin_daily.py \
		&& $(PYTHON_F) ping/import_admin_daily.py \
		&& $(PYTHON_F) ping/import_basin_6months.py \
		&& $(PYTHON_F) ping/import_admin_6months.py

# ── Clear all DB rows ─────────────────────────────────────────────────────────

clear-db: ## Delete ALL rows for both basins from all 24 DB tables
	cd $(HIST_DIR) && $(PYTHON_H) clear_db.py

# ── Reimport all — clear then reimport forecast + historical ──────────────────
# Use this when you have updated historical CSVs and want a clean reload.
# Does NOT re-run SWAT — reuses existing Results/ for forecast.
reimport-all: clear-db reimport-forecast import-historical ## Clear DB then reimport forecast + historical (no SWAT run)

# ── Historical (2022-2024) — INSERT only, reuses existing Results/ ────────────

import-historical: ## Historical: append 2022-2024 data for both basins (no SWAT re-run, no delete)
	cd $(HIST_DIR) && $(PYTHON_H) import_basin_7days.py \
		&& $(PYTHON_H) import_basin_6months.py \
		&& $(PYTHON_H) import_admin_7days.py \
		&& $(PYTHON_H) import_admin_6months.py \
		&& $(PYTHON_H) import_basin_daily.py \
		&& $(PYTHON_H) import_admin_daily.py

# ── Full pipeline — correct order: forecast first, then historical ─────────────
# Forecast does DELETE+INSERT (wipes per-basin rows), historical appends on top.
full-run: run-all-forecast import-historical ## Full pipeline: forecast (DELETE+INSERT) then historical append

# ── Utilities ─────────────────────────────────────────────────────────────────

download-drive: ## Download all zips from Google Drive into swat_file_DB/
	mkdir -p $(FILE_DB)
	gdown --folder $(DRIVE_URL) -O $(FILE_DB)

unpack-yom: ## Unpack yom_week/month_TxtInOut.zip into yom/week/ and yom/month/
	mkdir -p $(FORE_DIR)/yom/week  && unzip -o $(FILE_DB)/yom_week_TxtInOut.zip  -d $(FORE_DIR)/yom/week
	mkdir -p $(FORE_DIR)/yom/month && unzip -o $(FILE_DB)/yom_month_TxtInOut.zip -d $(FORE_DIR)/yom/month

unpack-ping: ## Unpack ping_week/month_TxtInOut.zip into ping/week/ and ping/month/
	mkdir -p $(FORE_DIR)/ping/week  && unzip -o $(FILE_DB)/ping_week_TxtInOut.zip  -d $(FORE_DIR)/ping/week
	mkdir -p $(FORE_DIR)/ping/month && unzip -o $(FILE_DB)/ping_month_TxtInOut.zip -d $(FORE_DIR)/ping/month

unpack-swat: ## Unpack swat_rev688.zip into swat_forecast/swat_rev688/
	unzip -o $(FILE_DB)/swat_rev688.zip -d $(FORE_DIR)

unpack-historical: ## Unpack ping/yom_historical.zip into historical_data/
	unzip -o $(FILE_DB)/ping_historical.zip -d $(ROOT_DIR)
	unzip -o $(FILE_DB)/yom_historical.zip  -d $(ROOT_DIR)

unpack-all: unpack-yom unpack-ping unpack-swat unpack-historical ## Unpack all zips (TxtInOut + swat_rev688 + historical data)

clear-ping: ## Delete all Ping (mb_code=06) rows from all DB tables
	cd $(HIST_DIR) && $(PYTHON_H) clear_basin.py ping

clear-yom: ## Delete all Yom (mb_code=08) rows from all DB tables
	cd $(HIST_DIR) && $(PYTHON_H) clear_basin.py yom

verify-db: ## Verify row counts and date ranges for all basins in DB
	cd $(HIST_DIR) && $(PYTHON_H) verify_db.py

print-swat-dir: ## Print resolved directory paths
	@echo "SWAT_DIR : $(SWAT_DIR)"
	@echo "FORE_DIR : $(FORE_DIR)"
	@echo "HIST_DIR : $(HIST_DIR)"

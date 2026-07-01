.DEFAULT_GOAL := help
.PHONY: help setup fix-permissions check-db \
        run-month-yom run-week-yom run-month-ping run-week-ping run-all-forecast \
        reimport-forecast reimport-all clear-db \
        download-drive unpack-yom unpack-ping unpack-swat unpack-historical unpack-all print-swat-dir \
        import-historical clear-ping clear-yom verify-db \
        full-run install-cron uninstall-cron show-cron \
        download-historical unpack-historical-chunk aggregate-historical add-historical pull-historical

ROOT_DIR  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
SWAT_DIR  := $(ROOT_DIR)/swat
FORE_DIR  := $(ROOT_DIR)/swat_forecast
HIST_DIR  := $(ROOT_DIR)/historical_data
FILE_DB   := $(ROOT_DIR)/swat_file_DB
DRIVE_URL      := https://drive.google.com/drive/folders/1fCaorGy1KrrjTyVYX00a8CO88SsqChTm
HIST_DRIVE_URL ?=
HIST_CHUNK_TMP := $(FILE_DB)/hist_chunk
PYTHON    = $(SWAT_DIR)/env/bin/python3
PYTHON_F  = $(FORE_DIR)/env/bin/python3
PYTHON_H  = $(HIST_DIR)/env/bin/python3

YOM_W_LOG := $(FORE_DIR)/yom/week/Logs
YOM_M_LOG := $(FORE_DIR)/yom/month/Logs
PNG_W_LOG := $(FORE_DIR)/ping/week/Logs
PNG_M_LOG := $(FORE_DIR)/ping/month/Logs

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  %-22s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## First-time setup: venv + download from Drive + unpack
	bash $(ROOT_DIR)/setup.sh

fix-permissions: ## Fix ownership if project was first touched by root (run once)
	sudo chown -R $(USER):$(USER) $(ROOT_DIR)

check-db: ## Test DB connection
	$(PYTHON_F) $(FORE_DIR)/check_db.py

# ── Forecast (live) — DELETE+INSERT per basin ────────────────────────────────

run-week-yom: ## Forecast: run Yom weekly SWAT + import to DB + summary email
	mkdir -p $(YOM_W_LOG) && rm -f $(YOM_W_LOG)/run_state.json
	(export SWAT_LOG_DIR=$(YOM_W_LOG) && \
	 cd $(FORE_DIR)/yom && $(PYTHON_F) week.py && \
	 cd $(FORE_DIR) && \
	 $(PYTHON_F) yom/import_basin_7days.py && \
	 $(PYTHON_F) yom/import_admin_7days.py && \
	 $(PYTHON_F) yom/import_basin_daily.py && \
	 $(PYTHON_F) yom/import_admin_daily.py) ; \
	$(PYTHON_F) $(FORE_DIR)/send_summary.py week yom

run-month-yom: ## Forecast: run Yom monthly SWAT + import to DB + summary email
	mkdir -p $(YOM_M_LOG) && rm -f $(YOM_M_LOG)/run_state.json
	(export SWAT_LOG_DIR=$(YOM_M_LOG) && \
	 cd $(FORE_DIR)/yom && $(PYTHON_F) month.py && \
	 cd $(FORE_DIR) && \
	 $(PYTHON_F) yom/import_basin_6months.py && \
	 $(PYTHON_F) yom/import_admin_6months.py && \
	 $(PYTHON_F) yom/import_basin_daily.py && \
	 $(PYTHON_F) yom/import_admin_daily.py) ; \
	$(PYTHON_F) $(FORE_DIR)/send_summary.py month yom

run-week-ping: ## Forecast: run Ping weekly SWAT + import to DB + summary email
	mkdir -p $(PNG_W_LOG) && rm -f $(PNG_W_LOG)/run_state.json
	(export SWAT_LOG_DIR=$(PNG_W_LOG) && \
	 cd $(FORE_DIR)/ping && $(PYTHON_F) week.py && \
	 cd $(FORE_DIR) && \
	 $(PYTHON_F) ping/import_basin_7days.py && \
	 $(PYTHON_F) ping/import_admin_7days.py && \
	 $(PYTHON_F) ping/import_basin_daily.py && \
	 $(PYTHON_F) ping/import_admin_daily.py) ; \
	$(PYTHON_F) $(FORE_DIR)/send_summary.py week ping

run-month-ping: ## Forecast: run Ping monthly SWAT + import to DB + summary email
	mkdir -p $(PNG_M_LOG) && rm -f $(PNG_M_LOG)/run_state.json
	(export SWAT_LOG_DIR=$(PNG_M_LOG) && \
	 cd $(FORE_DIR)/ping && $(PYTHON_F) month.py && \
	 cd $(FORE_DIR) && \
	 $(PYTHON_F) ping/import_basin_6months.py && \
	 $(PYTHON_F) ping/import_admin_6months.py && \
	 $(PYTHON_F) ping/import_basin_daily.py && \
	 $(PYTHON_F) ping/import_admin_daily.py) ; \
	$(PYTHON_F) $(FORE_DIR)/send_summary.py month ping

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

import-historical: ## Historical: insert aggregated CSV data into DB (insert only, no delete)
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

# ── Historical chunk management ───────────────────────────────────────────────

download-historical: ## Download historical zip from Drive into hist_chunk/ (requires: HIST_DRIVE_URL=<file-url>)
	@[ -n "$(HIST_DRIVE_URL)" ] || { echo "ERROR: HIST_DRIVE_URL is not set. Usage: make add-historical HIST_DRIVE_URL=https://drive.google.com/file/d/<id>/view"; exit 1; }
	mkdir -p $(HIST_CHUNK_TMP)
	cd $(HIST_CHUNK_TMP) && gdown "$(HIST_DRIVE_URL)"

unpack-historical-chunk: ## Unzip all zips in hist_chunk/ into historical_data/ (zip's top folder becomes chunk dir)
	@for z in $(HIST_CHUNK_TMP)/*.zip; do \
		[ -f "$$z" ] || { echo "No zip found in $(HIST_CHUNK_TMP)"; exit 1; }; \
		echo "Unpacking $$z → $(HIST_DIR)/"; \
		unzip -o "$$z" -d "$(HIST_DIR)"; \
	done

aggregate-historical: ## Aggregate all chunk dirs into master ping/ and yom/ files, then clean up hist_chunk/
	cd $(HIST_DIR) && $(PYTHON_H) aggregate.py
	rm -rf $(HIST_CHUNK_TMP)

add-historical: ## Full flow: download zip → unzip → aggregate → import (override: HIST_DRIVE_URL=<url>)
	$(MAKE) download-historical
	$(MAKE) unpack-historical-chunk
	$(MAKE) aggregate-historical
	$(MAKE) import-historical

# Example: make pull-historical HIST_DRIVE_URL="https://drive.google.com/file/d/1cUk4WpY17kDyfAE65I3QTmkbw8sW2y5i/view?usp=sharing"
pull-historical: ## Download + unzip only, no aggregate (for pre-merged zips) (override: HIST_DRIVE_URL=<url>)
	$(MAKE) download-historical
	$(MAKE) unpack-historical-chunk

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

install-cron: ## Install daily cron jobs for all pipelines + monthly log cleanup
	(crontab -l 2>/dev/null | grep -vF "$(ROOT_DIR)"; \
	 echo "0 1 * * *  cd $(ROOT_DIR) && make run-week-yom >> $(YOM_W_LOG)/cron.log 2>&1"; \
	 echo "2 1 * * *  cd $(ROOT_DIR) && make run-week-ping >> $(PNG_W_LOG)/cron.log 2>&1"; \
	 echo "5 1 * * *  cd $(ROOT_DIR) && make run-month-yom >> $(YOM_M_LOG)/cron.log 2>&1"; \
	 echo "10 1 * * *  cd $(ROOT_DIR) && make run-month-ping >> $(PNG_M_LOG)/cron.log 2>&1"; \
	 echo "15 1 * * *  find $(FORE_DIR)/*/*/Logs -name '*.log' -mtime +90 -delete") | crontab -
	@echo "Cron installed:"
	@crontab -l

uninstall-cron: ## Remove all cron jobs for this project (leaves other cron entries untouched)
	crontab -l 2>/dev/null | grep -vF "$(ROOT_DIR)" | crontab -
	@echo "Cron entries for $(ROOT_DIR) removed."

show-cron: ## Show current crontab
	@crontab -l 2>/dev/null | grep . || echo "(no crontab installed)"

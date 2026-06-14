#!/usr/bin/env python3
"""
Import daily admin forecast CSVs into DB (forecast_*_daily_* tables).

Week model reads from:  week/Results/
  Province_Daily.csv → forecast_province_daily_7days
  Amphoe_Daily.csv   → forecast_amphoe_daily_7days
  Tambol_Daily.csv   → forecast_tambon_daily_7days

Month model reads from:  month/Results/
  Province_Daily.csv → forecast_province_daily_6months
  Amphoe_Daily.csv   → forecast_amphoe_daily_6months
  Tambol_Daily.csv   → forecast_tambon_daily_6months
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _db import copy_insert, parse_date, read_csv, run, to_int, to_num

ROOT = Path(__file__).parent
log = logging.getLogger("SWAT_Weekly_Pipeline")

MODELS = {
    "7days":   ROOT / "week/Results",
    "6months": ROOT / "month/Results",
}

MB_CODES = ["08"]


def import_province(cur):
    results = []
    for suffix, results_dir in MODELS.items():
        table = f"forecast_province_daily_{suffix}"
        path = results_dir / "Province_Daily.csv"
        log.info(f"Province_Daily.csv → {table}")
        if not path.exists():
            log.warning(f"SKIP: {path} not found")
            continue
        columns = ["date_sim", "mb_code", "province_id", "province",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                "08",
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        log.info(f"SUCCESS: {len(rows)} rows → {table}")
        results.append({"table": table, "rows": len(rows)})
    return results


def import_amphoe(cur):
    results = []
    for suffix, results_dir in MODELS.items():
        table = f"forecast_amphoe_daily_{suffix}"
        path = results_dir / "Amphoe_Daily.csv"
        log.info(f"Amphoe_Daily.csv → {table}")
        if not path.exists():
            log.warning(f"SKIP: {path} not found")
            continue
        columns = ["date_sim", "mb_code", "amphoe_id", "amphoe", "province_id", "province",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                "08",
                str(row["Amphoe_ID"]).strip(),
                row.get("Amphoe") or None,
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        log.info(f"SUCCESS: {len(rows)} rows → {table}")
        results.append({"table": table, "rows": len(rows)})
    return results


def import_tambon(cur):
    results = []
    for suffix, results_dir in MODELS.items():
        table = f"forecast_tambon_daily_{suffix}"
        path = results_dir / "Tambol_Daily.csv"
        log.info(f"Tambol_Daily.csv → {table}")
        if not path.exists():
            log.warning(f"SKIP: {path} not found")
            continue
        columns = ["date_sim", "mb_code", "tambon_id", "tambon", "amphoe_id", "amphoe",
                   "province_id", "province",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                "08",
                str(row["Tambol_ID"]).strip(),
                row.get("Tambol") or None,
                str(row["Amphoe_ID"]).strip(),
                row.get("Amphoe") or None,
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        log.info(f"SUCCESS: {len(rows)} rows → {table}")
        results.append({"table": table, "rows": len(rows)})
    return results


if __name__ == "__main__":
    run([import_province, import_amphoe, import_tambon],
        log_dir=ROOT / "week" / "Logs",
        script_name="import_admin_daily")

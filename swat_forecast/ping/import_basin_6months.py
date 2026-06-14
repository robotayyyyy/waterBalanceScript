#!/usr/bin/env python3
"""
Import monthly SWAT results into DB (basin_*_6months tables).

Reads from:  month/Results/
  Bonwr_Monthly.csv           → basin_watershed_6months
  Sbonwr_Monthly.csv          → basin_subbasin_l1_6months
  Analysis_Sbswat_Monthly.csv → basin_subbasin_l2_6months
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _db import copy_insert, read_csv, run, to_int, to_num, year_mon_to_date, zero_pad_mb, zero_pad_sb

ROOT = Path(__file__).parent
log = logging.getLogger("SWAT_Weekly_Pipeline")

BASINS = {
    "Ping": {"results_dir": ROOT / "month/Results", "mb_code": "06"},
}

MB_CODES = [cfg["mb_code"] for cfg in BASINS.values()]


def import_watershed(cur):
    log.info("[1/3] Bonwr_Monthly.csv → basin_watershed_6months")
    columns = ["date_sim", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Bonwr_Monthly.csv"
        if not path.exists():
            log.warning(f"SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        log.info(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_watershed_6months WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_watershed_6months", columns, all_rows)
    log.info(f"SUCCESS: {len(all_rows)} rows → basin_watershed_6months")
    return {"table": "basin_watershed_6months", "rows": len(all_rows)}


def import_subbasin_l1(cur):
    log.info("[2/3] Sbonwr_Monthly.csv → basin_subbasin_l1_6months")
    columns = ["date_sim", "sb_code", "sb_name_t", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Sbonwr_Monthly.csv"
        if not path.exists():
            log.warning(f"SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        if not raw:
            log.warning(f"SKIP {basin}: file is empty")
            continue
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
                zero_pad_sb(row["SB_CODE"]),
                row.get("SB_NAME_T")    or None,
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        log.info(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_subbasin_l1_6months WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_subbasin_l1_6months", columns, all_rows)
    log.info(f"SUCCESS: {len(all_rows)} rows → basin_subbasin_l1_6months")
    return {"table": "basin_subbasin_l1_6months", "rows": len(all_rows)}


def import_subbasin_l2(cur):
    log.info("[3/3] Analysis_Sbswat_Monthly.csv → basin_subbasin_l2_6months")
    columns = ["date_sim", "sbswat", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Analysis_Sbswat_Monthly.csv"
        if not path.exists():
            log.warning(f"SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
                int(row["Sbswat"]),
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        log.info(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_subbasin_l2_6months WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_subbasin_l2_6months", columns, all_rows)
    log.info(f"SUCCESS: {len(all_rows)} rows → basin_subbasin_l2_6months")
    return {"table": "basin_subbasin_l2_6months", "rows": len(all_rows)}


if __name__ == "__main__":
    run([import_watershed, import_subbasin_l1, import_subbasin_l2],
        log_dir=ROOT / "month" / "Logs",
        script_name="import_basin_6months")

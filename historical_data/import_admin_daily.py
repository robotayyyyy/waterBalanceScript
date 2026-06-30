#!/usr/bin/env python3
"""
Import daily admin forecast CSVs into DB (forecast_*_daily_* tables).

For each basin, same file is inserted into both 7days and 6months tables.
  Province_Daily.csv → forecast_province_daily_7days, forecast_province_daily_6months
  Amphoe_Daily.csv   → forecast_amphoe_daily_7days,   forecast_amphoe_daily_6months
  Tambol_Daily.csv   → forecast_tambon_daily_7days,   forecast_tambon_daily_6months
"""

from pathlib import Path
from _db import copy_insert, copy_insert_stream, parse_date, read_csv, run, stream_csv, to_int, to_num

ROOT = Path(__file__).parent
DATA_DIR = Path(__file__).parent

BASINS = {
    "Ping": {"results_dir": DATA_DIR / "ping", "mb_code": "06"},
    "Yom":  {"results_dir": DATA_DIR / "yom" , "mb_code": "08"},
}

SUFFIXES = ["7days", "6months"]


def import_province(cur):
    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Province_Daily.csv"
        if not path.exists():
            print(f"\n  SKIP {basin} Province_Daily.csv: not found")
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
                cfg["mb_code"],
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
        for suffix in SUFFIXES:
            table = f"forecast_province_daily_{suffix}"
            print(f"\n  {basin} Province_Daily.csv → {table}")
            copy_insert(cur, table, columns, rows)
            print(f"    ✓ {len(rows)} rows inserted")


def import_amphoe(cur):
    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Amphoe_Daily.csv"
        if not path.exists():
            print(f"\n  SKIP {basin} Amphoe_Daily.csv: not found")
            continue
        columns = ["date_sim", "mb_code", "amphoe_id", "amphoe", "province_id", "province",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        for suffix in SUFFIXES:
            table = f"forecast_amphoe_daily_{suffix}"
            print(f"\n  {basin} Amphoe_Daily.csv → {table}")
            headers, raw = stream_csv(path)
            def _rows(headers=headers, raw=raw, cfg=cfg):
                for r in raw:
                    row = dict(zip(headers, r))
                    yield [
                        parse_date(row["DateSim"]),
                        cfg["mb_code"],
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
                    ]
            count = copy_insert_stream(cur, table, columns, _rows())
            print(f"    ✓ {count} rows inserted")


def import_tambon(cur):
    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Tambol_Daily.csv"
        if not path.exists():
            print(f"\n  SKIP {basin} Tambol_Daily.csv: not found")
            continue
        columns = ["date_sim", "mb_code", "tambon_id", "tambon", "amphoe_id", "amphoe",
                   "province_id", "province",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        for suffix in SUFFIXES:
            table = f"forecast_tambon_daily_{suffix}"
            print(f"\n  {basin} Tambol_Daily.csv → {table}")
            headers, raw = stream_csv(path)
            def _rows(headers=headers, raw=raw, cfg=cfg):
                for r in raw:
                    row = dict(zip(headers, r))
                    yield [
                        parse_date(row["DateSim"]),
                        cfg["mb_code"],
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
                    ]
            count = copy_insert_stream(cur, table, columns, _rows())
            print(f"    ✓ {count} rows inserted")


if __name__ == "__main__":
    run([import_province, import_amphoe, import_tambon])

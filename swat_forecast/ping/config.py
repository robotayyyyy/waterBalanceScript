import os
from pathlib import Path

# =====================================================================
# SYSTEM PATHS & ENVIRONMENTS
# =====================================================================
# 1. Read the mode (Defaults to 'week' if not specified)
SWAT_MODE = os.environ.get("SWAT_MODE", "week")
SCRIPT_DIR = Path(__file__).absolute().parent

# 2. Dynamically set the Base Directory
BASE_DIR = (SCRIPT_DIR / SWAT_MODE).resolve()

RAW_INPUT_DIR = BASE_DIR / "Import_input" 
IMPORTED_CSV_DIR = BASE_DIR / "Imported" 
TXTINOUT_DIR = BASE_DIR / "TxtInOut"
EXECUTABLE_PATH = (SCRIPT_DIR.parent / "swat_rev688" / "rev688_64rel_linux").resolve()

INPUT_DIR = SCRIPT_DIR / "Inputs"
FLOW_DIR = INPUT_DIR / "Flow"
RELEASE_DIR = INPUT_DIR / "Release"
LOG_DIR = BASE_DIR / "Logs"
FINAL_OUTPUT_DIR = BASE_DIR / "Results"
STAGING_DIR = BASE_DIR / "Results_staging"
ALERT_DIR = BASE_DIR / "Alerts"

WARMUP_DAYS = 90
# 3. Dynamically set forecast days ( 7 for week, 180 for month)
FORECAST_DAYS = 7 if SWAT_MODE == "week" else 180

def get_pipeline_paths():
    paths = {
        'wus_raw': INPUT_DIR / "wus.csv",
        'thresh_drought': INPUT_DIR / "drought_thershold.csv",
        'frac_admin': INPUT_DIR / "fraction.csv",
        'frac_onwr': INPUT_DIR / "SBfraction.csv",

        'rain_raw_imported': IMPORTED_CSV_DIR / "rain.csv",
        'rain_tambol_imported': IMPORTED_CSV_DIR / "rain_Tambol.csv",
        'rain_amphoe_imported': IMPORTED_CSV_DIR / "rain_Amphoe.csv",
        'rain_province_imported': IMPORTED_CSV_DIR / "rain_Province.csv",
        'rain_sbonwr_imported': IMPORTED_CSV_DIR / "rain_Sbonwr.csv",
        'rain_bonwr_imported': IMPORTED_CSV_DIR / "rain_bonwr.csv",
        
        'water_supply': STAGING_DIR / "water_supply.csv",
        'water_demand': STAGING_DIR / "water_demand.csv",
        'water_balance': STAGING_DIR / "water_balance.csv",
        'runoff_idx': STAGING_DIR / "runoff_index.csv",
        'drought_idx': STAGING_DIR / "drought_index.csv",
        'reservoir_idx': STAGING_DIR / "reservoir.csv",
        'rainfall_idx': STAGING_DIR / "rainfall.csv",
        'analysis_base': STAGING_DIR / "Analysis_Sbswat.csv"
    }

    # 4. Automatically generate Day and Week/Month threshold paths
    paths['wb_level_idx'] = STAGING_DIR / "wb_level_index.csv"
    levels = ["Sbswat", "Tambol", "Amphoe", "Province", "SB", "MB"]
    for level in levels:
        key_base = level.lower()
        
        # Runoff Thresholds
        paths[f'thresh_{key_base}_day'] = INPUT_DIR / "runoff/day" / f"{level}_critical.csv"
        paths[f'thresh_{key_base}_{SWAT_MODE}'] = INPUT_DIR / f"runoff/{SWAT_MODE}" / f"{level}_critical.csv"
        
        # Water Balance Level Thresholds
        paths[f'thresh_wb_{key_base}_day'] = INPUT_DIR / "WB_level/day" / f"{level}_wb_level.csv"
        paths[f'thresh_wb_{key_base}_{SWAT_MODE}'] = INPUT_DIR / f"WB_level/{SWAT_MODE}" / f"{level}_wb_level.csv"

    # 5. FLOW : water management data paths
    flow_sid = [540]
    paths['flow_csv'] = {
        sub_id: FLOW_DIR / f"{sub_id}.csv" 
        for sub_id in flow_sid
    }
    
    # Map subbasin ID to its target SWAT output file (e.g., TxtInOut/617p.dat)
    paths['dot_dat'] = {
        sub_id: TXTINOUT_DIR / f"{sub_id}p.dat" 
        for sub_id in flow_sid
    }
    
    # 6. RELEASE : water management data paths
    release_id = [4,42,70,73,177,213,317,320,361,362,371,389,432,443,445,523,600]
    paths['release_csv'] = {
        sub_id: RELEASE_DIR / f"{sub_id}.csv" 
        for sub_id in release_id
    }
    
    # Map subbasin ID to its target SWAT output file (e.g., TxtInOut/005950000.day)
    paths['dot_day'] = {
        sub_id: TXTINOUT_DIR / f"00{int(sub_id):03d}0000.day" 
        for sub_id in release_id
    }
        
    return paths
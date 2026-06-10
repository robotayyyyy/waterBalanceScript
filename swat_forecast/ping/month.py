import shutil
import sys
import os
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# SET MODE BEFORE IMPORTING CONFIG! ("week" or "month")
os.environ["SWAT_MODE"] = "month"

from config import BASE_DIR, RAW_INPUT_DIR, IMPORTED_CSV_DIR, TXTINOUT_DIR, EXECUTABLE_PATH, INPUT_DIR, LOG_DIR, FINAL_OUTPUT_DIR, STAGING_DIR, ALERT_DIR, WARMUP_DAYS, FORECAST_DAYS, get_pipeline_paths
from utils import setup_colored_logger, load_basin_mapping

from simulation import get_project_dates, run_data_import, run_write_input, run_swat_simulation
from analysis import run_swat_analysis

if __name__ == "__main__":
    # Bootstrap Directories
    for d in [RAW_INPUT_DIR, IMPORTED_CSV_DIR, STAGING_DIR]:
        if d.exists(): shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    for d in [LOG_DIR, ALERT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    log_file_path = LOG_DIR / f"swat_{os.environ['SWAT_MODE']}_master_pipeline_{today_str}.log"
    logger = setup_colored_logger(log_file=str(log_file_path))

    # Phase Tasks & Parameters
    input_files = ["rain.csv", "temp.csv", "rh.csv", "wind.csv", "solar.csv"]
    swat_tasks = [
        ("rain.csv", "pcp1.pcp", "pcp"),
        ("temp.csv", "tmp1.tmp", "temp"), 
        ("rh.csv",   "hmd.hmd", "rh"),
        ("wind.csv", "wnd.wnd", "wind"),
        ("solar.csv","slr.slr", "solar")
    ]
    
    # Grab all automatically generated paths (Including flow_csv, dot_day, release_csv, dot_dat)
    paths = get_pipeline_paths()

    try:
        # Step 1.1: Download, Check, and Save to Import Folder
        run_data_import(basin_id="06", input_dir=str(RAW_INPUT_DIR), imported_dir=str(IMPORTED_CSV_DIR), files=input_files, alert_dir=str(ALERT_DIR), logger=logger)
        
        # Step 1.2: Find Simulation Date
        sim_start, sim_end, f_start, f_end = get_project_dates(str(IMPORTED_CSV_DIR))
        
        # Step 1.3: Write Inputs for SWAT (Climate, Reservoir, and Point Source files)
        run_write_input(
            imported_dir=str(IMPORTED_CSV_DIR), 
            txt_in_out_dir=str(TXTINOUT_DIR), 
            tasks=swat_tasks, 
            start_date=sim_start, 
            end_date=sim_end, 
            alert_dir=str(ALERT_DIR), 
            logger=logger,
            flow_csv=paths.get('flow_csv'),
            dot_dat=paths.get('dot_dat'),
            release_csv=paths.get('release_csv'),
            dot_day=paths.get('dot_day')
        )        
        
        # Step 1.4: Run Fortran Executable
        sim_success = run_swat_simulation(str(TXTINOUT_DIR), str(EXECUTABLE_PATH), sim_start, sim_end, str(ALERT_DIR), logger)

        if not sim_success:
            logger.error("Simulation Failed. Analysis will not proceed.")
            sys.exit(1)

        # Step 2: Run Analysis Pipeline
        res_map = load_basin_mapping(str(INPUT_DIR / "res_mapping.json"))

        basin_config = {
            'mb_code': '06',
            'mb_name_t': 'ปิง',
            'total_subbasins': 612,
            'actual_print_start_year': sim_start.year,
            'res_to_sub_map': res_map,
            'forecast_start': f_start,
            'forecast_end': f_end
        }

        state_tracker, pipeline_failed = run_swat_analysis(
            txtinout_dir=TXTINOUT_DIR, 
            output_dir=STAGING_DIR, 
            inputs=paths, 
            config=basin_config, 
            alert_dir=ALERT_DIR, 
            logger=logger)
        
        if pipeline_failed:
                logger.error("Analysis FAILED, The final 'Results' folder was NOT updated.")
        else:
            if FINAL_OUTPUT_DIR.exists(): shutil.rmtree(FINAL_OUTPUT_DIR)
            STAGING_DIR.rename(FINAL_OUTPUT_DIR)
            logger.info("SUCCESS: Final 'Results' directory successfully updated.")

    except Exception as fatal_e:
        logger.error(f"FATAL PIPELINE ERROR: {str(fatal_e)}")
        sys.exit(1)
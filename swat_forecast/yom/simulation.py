import os
import re
import sys
import requests
import zipfile
import io
import shutil
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from utils import generate_email_alert, _date_to_julian

# Globally detect if we are running in Monthly or Weekly mode
SWAT_MODE = os.environ.get("SWAT_MODE", "week")
HII_BASE_URL = os.getenv("HII_BASE_URL", "https://tiservice.hii.or.th/water_balance")

def get_project_dates(input_dir, reference_keyword="rain", warmup_days=90):
    filepath = None
    for file in os.listdir(input_dir):
        if reference_keyword.lower() in file.lower() and file.endswith('.csv'):
            filepath = os.path.join(input_dir, file)
            break
            
    if not filepath:
        raise FileNotFoundError(f"No file containing '{reference_keyword}' found in {input_dir}")
        
    df = pd.read_csv(filepath, usecols=['date'])
    max_data_date = pd.to_datetime(df['date'].astype(str), format='%Y%m%d').max()
    sim_end = max_data_date
    
    # DYNAMIC ROUTING FOR DATES
    if SWAT_MODE == "month":
        forecast_days = 180
        sim_start = sim_end - timedelta(days=(warmup_days + forecast_days - 1))
        f_start = (sim_end - timedelta(days=forecast_days)).replace(day=1)
        f_end = sim_end.replace(day=1)
    else:
        forecast_days = 7
        sim_start = sim_end - timedelta(days=(warmup_days + forecast_days - 1))
        f_start = sim_end - timedelta(days=forecast_days - 1)
        f_end = sim_end
        
    return sim_start, sim_end, f_start, f_end

def run_data_import(basin_id, input_dir, imported_dir, files, alert_dir, logger):
    logger.info(f"{SWAT_MODE.capitalize()} Import started")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(imported_dir, exist_ok=True)
    state_tracker = {}
    
    # DYNAMIC ROUTING FOR DOWNLOADS
    if SWAT_MODE == "month":
        target_date = datetime.now()
        yyyymm = target_date.strftime("%Y%m")
        zip_filename = f"Basin{basin_id}_M_{yyyymm}.zip"
        url = f"{HII_BASE_URL}/sixmonth/{yyyymm}/{zip_filename}"
        logger.info(f"Targeting monthly data folder: {yyyymm}")
    else:
        base_url = f"{HII_BASE_URL}/oneweek/"
        try:
            dir_response = requests.get(base_url, timeout=30)
            dir_response.raise_for_status()
            date_folders = re.findall(r'(\d{8})/?', dir_response.text)
            if not date_folders: raise ValueError("No valid date folders (YYYYMMDD) found.")
            yyyymmdd = sorted(list(set(date_folders)))[-1]
            logger.info(f"Targeting newest weekly data folder: {yyyymmdd}")
            zip_filename = f"Basin{basin_id}_W_{yyyymmdd}.zip"
            url = f"{base_url}{yyyymmdd}/{zip_filename}"
        except Exception as e:
            logger.error(f"Folder Discovery FAILED: {str(e)}")
            state_tracker["Folder Discovery"] = {"status": "FAILED", "error": str(e)}
            generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_import.txt"), phase_name="Folder Discovery")
            raise e

    try:
        logger.info(f"Downloading data from: {url}")
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                z.extractall(input_dir)
        else:
            logger.error(f"Download FAILED: HTTP {response.status_code}")
            state_tracker["Download"] = {"status": "FAILED", "error": f"HTTP {response.status_code}"}
            generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_import.txt"), phase_name="Download Data")
            raise Exception(f"HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Download FAILED: {str(e)}")
        state_tracker["Download"] = {"status": "FAILED", "error": str(e)}
        generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_import.txt"), phase_name="Download Data")
        raise e

    raw_files = os.listdir(input_dir)
    extra_rain_keywords = ["Tambol", "Amphoe", "Province", "Sbonwr", "bonwr"]
    
    for filename in files:
        log_name = filename.capitalize()
        base_keyword = filename.split('.')[0].lower()
        
        # DYNAMIC ROUTING FOR FILE MATCHING
        if SWAT_MODE == "month":
            matching_files = [rf for rf in raw_files if base_keyword in rf.lower() and "6month" in rf.lower() and "sbswat" in rf.lower() and rf.endswith('.csv')]
        else:
            matching_files = [rf for rf in raw_files if base_keyword in rf.lower() and 'sbswat' in rf.lower() and rf.endswith('.csv')]
        
        actual_raw_file = None
        if matching_files:
            matching_files.sort(reverse=True)
            actual_raw_file = matching_files[0]
                
        state_tracker[filename] = {"status": "FAILED", "error": "File not found"}
        
        if not actual_raw_file:
            logger.error(f"{log_name} loaded → FAILED (Main file not found)")
            continue
            
        filepath = os.path.join(input_dir, actual_raw_file)
        
        try:
            df = pd.read_csv(filepath)
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
            df.dropna(axis=1, how='all', inplace=True)
            
            data_cols = [c for c in df.columns if str(c).lower() != 'date']
            missing_days = df[data_cols].isna().any(axis=1).sum()
            
            if missing_days > 0:
                logger.warning(f"{log_name} loaded → Missing {missing_days} days data")
                state_tracker[filename] = {"status": "WARNING", "error": f"Missing {missing_days} days"}
            else:
                logger.info(f"{log_name} loaded → SUCCESS")
                state_tracker[filename] = {"status": "SUCCESS", "error": ""}
                
            out_path = os.path.join(imported_dir, filename)
            df.to_csv(out_path, index=False)
            
            folder_name = os.path.basename(imported_dir)
            logger.info(f"{log_name} saved to {folder_name}/{filename} → SUCCESS")
            
            if base_keyword == 'rain':
                for extra in extra_rain_keywords:
                    extra_out_name = f"rain_{extra}.csv"
                    extra_log_name = f"Rain_{extra}"
                    
                    if SWAT_MODE == "month":
                        extra_match = [rf for rf in raw_files if 'rain' in rf.lower() and "6month" in rf.lower() and extra.lower() in rf.lower() and rf.endswith('.csv')]
                    else:
                        extra_match = [rf for rf in raw_files if 'rain' in rf.lower() and extra.lower() in rf.lower() and rf.endswith('.csv')]
                    
                    if extra_match:
                        extra_match.sort(reverse=True)
                        extra_filepath = os.path.join(input_dir, extra_match[0])
                        
                        try:
                            df_extra = pd.read_csv(extra_filepath)
                            df_extra = df_extra.loc[:, ~df_extra.columns.str.contains('^Unnamed')]
                            df_extra.dropna(axis=1, how='all', inplace=True)
                            
                            extra_out_path = os.path.join(imported_dir, extra_out_name)
                            df_extra.to_csv(extra_out_path, index=False)
                            
                            logger.info(f"{extra_log_name} saved to {folder_name}/{extra_out_name} → SUCCESS")
                            state_tracker[extra_out_name] = {"status": "SUCCESS", "error": ""}
                        except Exception as e:
                            logger.error(f"{extra_log_name} loaded → FAILED ({str(e)})")
                            state_tracker[extra_out_name] = {"status": "FAILED", "error": str(e)}
                    else:
                        logger.warning(f"rain file for {extra} not found in zip.")
                        state_tracker[extra_out_name] = {"status": "WARNING", "error": "File not found"}

        except Exception as e:
            logger.error(f"{log_name} loaded → FAILED ({str(e)})")
            state_tracker[filename] = {"status": "FAILED", "error": str(e)}
            
    alert_path = os.path.join(alert_dir, "email_alert_import.txt")
    generate_email_alert(state_tracker, alert_path, phase_name="Import Data")
    print()

def fill_stat_data(df, variable_type, start_date, end_date):
    df = df.copy()
    df.index = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')
    
    # DYNAMIC ROUTING FOR START DATE
    file_start_date = datetime(start_date.year, 1, 1) if SWAT_MODE == "month" else start_date
    file_end_date = end_date
    
    mask = (df.index >= file_start_date) & (df.index <= file_end_date)
    df = df.loc[mask].copy()
    
    full_date_range = pd.date_range(start=file_start_date, end=file_end_date, freq='D')
    df = df.reindex(full_date_range)
    df['date'] = df.index.strftime('%Y%m%d').astype(int)
    
    forecast_days = 180 if SWAT_MODE == "month" else 7
    historical_end_date = end_date - timedelta(days=forecast_days)
    sim_mask_historical = (df.index >= start_date) & (df.index <= historical_end_date)
    
    if not df.loc[sim_mask_historical].empty:
        missing_days_count = df.loc[sim_mask_historical].drop(columns=['date']).isna().any(axis=1).sum()
    else:
        missing_days_count = 0

    cols_to_fill = [col for col in df.columns if col != 'date']

    if df[cols_to_fill].isna().any(axis=1).sum() > 0:
        if variable_type in ['temp', 'rh', 'solar', 'wind']:
            df[cols_to_fill] = df[cols_to_fill].interpolate(method='linear', limit=3)
        elif variable_type == 'pcp':
            spatial_daily_mean = df[cols_to_fill].mean(axis=1)
            for col in cols_to_fill:
                df[col] = df[col].fillna(spatial_daily_mean)

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    if variable_type in ['pcp', 'temp']:
        df[cols_to_fill] = df[cols_to_fill].clip(lower=-99.0, upper=999.9)
    else:
        df[cols_to_fill] = df[cols_to_fill].clip(lower=-99.0, upper=9999.999)

    df.reset_index(drop=True, inplace=True)
    df.fillna(-99.0, inplace=True) 
    
    return df, missing_days_count

def write_weather_data(imported_dir, txt_in_out_dir, tasks, start_date, end_date, logger, state_tracker):
    """Helper function to write climate variables."""
    for csv_file, swat_file, var_type in tasks:
        csv_path = os.path.join(imported_dir, csv_file)
        state_tracker[swat_file] = {"status": "FAILED", "error": "CSV missing"}
        
        if not os.path.exists(csv_path):
            csv_path = os.path.join(imported_dir, csv_file.capitalize())
            if not os.path.exists(csv_path): 
                continue
            
        target_swat_file = os.path.join(txt_in_out_dir, swat_file)
        backup_file = target_swat_file + ".bak"
        log_csv_name = os.path.basename(csv_path).capitalize()
            
        try:
            if not os.path.exists(backup_file):
                if os.path.exists(target_swat_file):
                    shutil.copy2(target_swat_file, backup_file)
                    logger.debug(f"Created Golden Backup for {swat_file}")
                else:
                    logger.error(f"Missing base file: {target_swat_file}")
                    state_tracker[swat_file] = {"status": "FAILED", "error": "Missing base SWAT file for backup"}
                    continue
            
            headers = []
            with open(backup_file, 'r') as f:
                header_lines = 4 if var_type in ['pcp', 'temp'] else 1
                headers = [next(f).rstrip('\r\n') + '\r\n' for _ in range(header_lines)]
            
            df = pd.read_csv(csv_path)
            df, missing_count = fill_stat_data(df, var_type, start_date, end_date)
            
            data_cols = [col for col in df.columns if col != 'date']
            
            with open(target_swat_file, 'w', newline='\r\n') as f:
                f.writelines(headers)
                format_str = "{:05.1f}" if var_type in ['pcp', 'temp'] else "{:08.3f}"
                
                for _, row in df.iterrows():
                    date_julian = _date_to_julian(row['date'])
                    values = "".join([format_str.format(row[c]) for c in data_cols])
                    f.write(f"{date_julian}{values}\n")
            
            if missing_count > 0:
                logger.warning(f"{log_csv_name} written to {swat_file} → Missing {missing_count} days data: Gap Filling Applied")
                state_tracker[swat_file] = {"status": "WARNING", "error": f"Gap-filled {missing_count} days"}
            else:
                logger.info(f"{log_csv_name} written to {swat_file} → SUCCESS")
                state_tracker[swat_file] = {"status": "SUCCESS", "error": ""}
                
        except Exception as e:
            logger.error(f"{log_csv_name} written to {swat_file} → FAILED ({str(e)})")
            state_tracker[swat_file] = {"status": "FAILED", "error": str(e)}


def write_dot_day(release_csv, dot_day, start_date, end_date, logger, state_tracker):
    """Helper function to write reservoir .day files."""
    for sub_id, csv_path in release_csv.items():
        target_swat_file = dot_day[sub_id]
        
        swat_day_filename = os.path.basename(target_swat_file)
        template_filename = os.path.basename(csv_path)
        
        if not os.path.exists(csv_path):
            logger.warning(f"SWAT inputfile '{template_filename}' not found. Skipping Subbasin {sub_id}.")
            state_tracker[swat_day_filename] = {"status": "WARNING", "error": f"Missing SWAT inputfile {template_filename}"}
            continue
            
        try:
            df_template = pd.read_csv(csv_path)
            lookup = df_template.set_index(['month', 'day'])['release'].to_dict()
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            values = [lookup.get((d.month, d.day), -99.0) for d in dates]
            
            with open(target_swat_file, 'w') as f:
                sim_start = start_date.strftime('%m/%d/%Y')
                sim_end = end_date.strftime('%m/%d/%Y')
                header = f"Daily Reservoir Outflow file:     .day file Subbasin:{sub_id}  {sim_start} to {sim_end}\n"
                f.write(header)
                for val in values:
                    f.write(f"{val:>10.3f}\n")
                    
            logger.info(f"{template_filename} written to {swat_day_filename} → SUCCESS")
            state_tracker[swat_day_filename] = {"status": "SUCCESS", "error": ""}
            
        except Exception as e:
            logger.error(f"{template_filename} written to {swat_day_filename} → FAILED ({str(e)})")
            state_tracker[swat_day_filename] = {"status": "FAILED", "error": str(e)}


def write_dot_dat(flow_csv, dot_dat, start_date, end_date, logger, state_tracker):
    """Helper function to write point source .dat files with 28 variables."""
    for sub_id, csv_path in flow_csv.items():
        target_swat_file = dot_dat[sub_id]
        
        swat_dat_filename = os.path.basename(target_swat_file)
        template_filename = os.path.basename(csv_path)
        
        if not os.path.exists(csv_path):
            logger.warning(f"SWAT inputfile '{template_filename}' not found. Skipping Subbasin {sub_id}.")
            state_tracker[swat_dat_filename] = {"status": "WARNING", "error": f"Missing SWAT inputfile {template_filename}"}
            continue
            
        try:
            # 1. Load CSV template
            df_template = pd.read_csv(csv_path)    
            lookup = df_template.set_index(['month', 'day'])['flow'].to_dict()
            
            # 2. Generate date sequence
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            
            # 3. Write .dat file
            with open(target_swat_file, 'w') as f:
                sim_start = start_date.strftime('%m/%d/%Y')
                f.write(f"{sim_start} 12:00:00 AM .dat file Daily Record Subbasin  {sub_id} ArcSWAT 2012.10_2.19 interface\n")
                f.write("\n\n\n\n")
                
                col_names = " DAY YEAR           FLODAY           SEDDAY          ORGNDAY          ORGPDAY           NO3DAY           NH3DAY           NO2DAY          MINPDAY          CBODDAY         DISOXDAY          CHLADAY        SOLPSTDAY        SRBPSTDAY         BACTPDAY        BACTLPDAY         CMTL1DAY         CMTL2DAY         CMTL3DAY         SALT1DAY         SALT2DAY         SALT3DAY         SALT4DAY         SALT5DAY         SALT6DAY         SALT7DAY         SALT8DAY         SALT9DAY        SALT10DAY\n"
                f.write(col_names)
                
                # 4. Format Daily Rows (27 parameters set to zero in scientific notation)
                empty_params = " ".join(["0.0000000000E+00" for _ in range(27)])
                
                for d in dates:
                    julian_day = d.timetuple().tm_yday
                    year = d.year
                    flow_val = lookup.get((d.month, d.day), 0.0)
                    
                    # Convert to required 10-decimal scientific notation
                    formatted_flow = f"{float(flow_val):.10E}"
                    
                    line = f"{julian_day:>4} {year} {formatted_flow} {empty_params}\n"
                    f.write(line)
                    
            logger.info(f"{template_filename} written to {swat_dat_filename} → SUCCESS")
            state_tracker[swat_dat_filename] = {"status": "SUCCESS", "error": ""}
            
        except Exception as e:
            logger.error(f"{template_filename} written to {swat_dat_filename} → FAILED ({str(e)})")
            state_tracker[swat_dat_filename] = {"status": "FAILED", "error": str(e)}

# =========================================================================
# THE UPDATED ORCHESTRATOR
# NOTE: The signature now includes the 4 new kwargs: flow_csv, dot_day, release_csv, dot_dat
# =========================================================================
def run_write_input(imported_dir, txt_in_out_dir, tasks, start_date, end_date, alert_dir, logger, flow_csv=None, dot_dat=None, release_csv=None, dot_day=None):
    logger.info("Writing SWAT Input Files...")
    state_tracker = {}
    
    loaded_files = [t[0].capitalize() for t in tasks if os.path.exists(os.path.join(imported_dir, t[0])) or os.path.exists(os.path.join(imported_dir, t[0].capitalize()))]
    logger.info(f"Input loaded: {', '.join(loaded_files)}")
    
    # ======== PART 1: CLIMATE & WEATHER FILES ==============================
    write_weather_data(
        imported_dir=imported_dir, 
        txt_in_out_dir=txt_in_out_dir, 
        tasks=tasks, 
        start_date=start_date, 
        end_date=end_date, 
        logger=logger, 
        state_tracker=state_tracker # Passed by reference
    )
        
    # ======== PART 2: RESERVOIR MANAGEMENT FILES (.day) ====================
    if release_csv and dot_day:
        logger.info("Processing Reservoir Management Files (.day)...")
        write_dot_day(
            release_csv=release_csv,
            dot_day=dot_day,
            start_date=start_date,
            end_date=end_date,
            logger=logger,
            state_tracker=state_tracker
        )
        
    # ======== PART 3: POINT SOURCE FILES (.dat) ============================
    if flow_csv and dot_dat:
        logger.info("Processing Point Source Files (.dat)...")
        write_dot_dat(
            flow_csv=flow_csv,
            dot_dat=dot_dat,
            start_date=start_date,
            end_date=end_date,
            logger=logger,
            state_tracker=state_tracker
        )
            
    # Send consolidated alert at the very end
    alert_path = os.path.join(alert_dir, "email_alert_write.txt")
    generate_email_alert(state_tracker, alert_path, phase_name="SWAT File Write")
    print()

def write_config(cio_path, start_date, end_date):
    iyr = start_date.year
    nbyr = end_date.year - start_date.year + 1
    idaf = start_date.timetuple().tm_yday
    idal = end_date.timetuple().tm_yday
    nyskip = 0

    updates = {"NBYR": nbyr, "IYR": iyr, "IDAF": idaf, "IDAL": idal, "NYSKIP": nyskip, "IPRINT": 1}
    
    with open(cio_path, 'r') as f: 
        lines = f.readlines()
        
    with open(cio_path, 'w') as f:
        for line in lines:
            updated = False
            if '|' in line:
                right_stripped = line.split('|', 1)[1].strip()
                for key, val in updates.items():
                    if re.match(rf"^{key}\b", right_stripped):
                        f.write(f"{val:>16}    |{line.split('|', 1)[1]}")
                        updated = True
                        break
            if not updated: 
                f.write(line)

def run_swat_simulation(txtinout_dir, executable_path, start_date, end_date, alert_dir, logger):
    date_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    logger.info(f"SWAT Execution started ({date_str})")
    state_tracker = {"Update file.cio": {"status": "NOT EXECUTED"}, "Execute Fortran": {"status": "NOT EXECUTED"}}
    
    cio_path = os.path.join(txtinout_dir, "file.cio")

    if os.path.exists(cio_path):
        try:
            write_config(cio_path, start_date, end_date)
            state_tracker["Update file.cio"] = {"status": "SUCCESS", "error": ""}
        except Exception as e:
            state_tracker["Update file.cio"] = {"status": "FAILED", "error": str(e)}
    else:
        logger.error("file.cio not found in TxtInOut. Cannot start simulation → FAILED")
        state_tracker["Update file.cio"] = {"status": "FAILED", "error": "file.cio missing"}
        generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_simulation.txt"), phase_name="SWAT Execution")
        return False

    try:
        process = subprocess.Popen([executable_path], cwd=txtinout_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ''):
            if "Executing year" in line:
                year_num = line.strip().split()[-1]
                logger.debug(f"Executing year {year_num}")
        process.wait()

        if process.returncode == 0:
            logger.info("Execution successfully completed")
            logger.info("Simulation Process: SUCCESS")
            state_tracker["Execute Fortran"] = {"status": "SUCCESS", "error": ""}
            success = True
        else:
            logger.error(f"Execution failed: SWAT return code != 0 (Code: {process.returncode}) → FAILED")
            state_tracker["Execute Fortran"] = {"status": "FAILED", "error": f"Return code {process.returncode}"}
            success = False
            
    except Exception as e:
        logger.error(f"Execution failed: {str(e)} → FAILED")
        state_tracker["Execute Fortran"] = {"status": "FAILED", "error": str(e)}
        success = False
        
    generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_simulation.txt"), phase_name="SWAT Execution")
    return success
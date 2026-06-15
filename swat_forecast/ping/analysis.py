import pandas as pd
import numpy as np
import os
import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import update_state, get_mode_or_mean, generate_email_alert

# Globally detect if we are running in Monthly or Weekly mode
SWAT_MODE = os.environ.get("SWAT_MODE", "week")

# ==========================================
# SWAT Output Stream Parser
# ==========================================
def stream_swat_data(input_file, output_csv, prefix, id_col, day_col, target_cols, start_year, is_hru=False):
    headers = ['YEAR', 'DAY'] + list(target_cols.keys()) if is_hru else [prefix.strip() if prefix else 'ID', 'YEAR', 'DAY'] + list(target_cols.keys())
    unit_year_tracker = {}
    records_saved = 0
    
    with open(input_file, 'r') as infile, open(output_csv, 'w', newline='') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(headers)
        
        for line_num, line in enumerate(infile):
            if line_num < 9: continue 
            if is_hru and len(line) > 34: line = line[:34] + ' ' + line[34:]
                
            parts = line.split()
            if len(parts) < max(target_cols.values()) + 1: continue
            if prefix and not line.startswith(prefix): continue
                
            try:
                day_float = float(parts[day_col])
                unit_id = int(parts[id_col])
            except (IndexError, ValueError): continue

            day_val = int(day_float)
            if day_val > 366 or day_val <= 0: continue

            if unit_id not in unit_year_tracker:
                unit_year_tracker[unit_id] = {'year': start_year, 'prev_day': 0}

            state = unit_year_tracker[unit_id]
            if day_val < state['prev_day'] and state['prev_day'] >= 300:
                state['year'] += 1

            state['prev_day'] = day_val
            current_year = state['year']
            
            try:
                if is_hru:
                    row_data = [
                        current_year, day_val, 
                        parts[target_cols['LULC']], int(parts[target_cols['Sbswat']]), 
                        float(parts[target_cols['AREAkm2']]), float(parts[target_cols['Rainfall_mm']]), 
                        float(parts[target_cols['ETmm']]), float(parts[target_cols['W_STRS']])
                    ]
                else:
                    row_data = [unit_id, current_year, day_val] + [float(parts[col_idx]) for col_name, col_idx in target_cols.items()]
                writer.writerow(row_data)
                records_saved += 1
            except ValueError: continue
    return records_saved

def load_outputs(txtinout_dir, output_dir, start_year):
    try:
        stream_swat_data(txtinout_dir / "output.rch", output_dir / "rch.csv", 'REACH', 1, 3, {'FLOW_INcms': 5, 'FLOW_OUTcms': 6}, start_year)
        stream_swat_data(txtinout_dir / "output.hru", output_dir / "hru.csv", None, 1, 5, {'LULC': 0, 'Sbswat': 3, 'AREAkm2': 6, 'Rainfall_mm': 7, 'ETmm': 12, 'W_STRS': 66}, start_year, True)
        stream_swat_data(txtinout_dir / "output.rsv", output_dir / "rsv.csv", 'RES', 1, 2, {'VOLUMEm3': 3}, start_year)
        return True
    except Exception:
        return False

def load_and_melt_rain_daily(rain_csv, id_col_name, f_start, f_end, logger):
    try:
        if not os.path.exists(rain_csv): 
            logger.warning(f"Rain file not found: {rain_csv}")
            return None
        df = pd.read_csv(rain_csv)
        if 'date' not in df.columns: return None
        
        date_series = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')
        mask = (date_series >= pd.to_datetime(f_start)) & (date_series <= pd.to_datetime(f_end))
        df_filtered = df.loc[mask].copy()
        if df_filtered.empty: return None
        
        df_filtered['DateSim'] = date_series.loc[mask].dt.strftime('%d/%m/%Y')
        df_filtered = df_filtered.drop(columns=['date'])
        df_summed = df_filtered.groupby('DateSim').sum().reset_index()
        
        df_long = df_summed.melt(id_vars=['DateSim'], var_name=id_col_name, value_name='Rainfall')
        df_long[id_col_name] = pd.to_numeric(df_long[id_col_name].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
        df_long = df_long.dropna(subset=[id_col_name])
        df_long['Rainfall'] = df_long['Rainfall'].round(3)
        return df_long[['DateSim', id_col_name, 'Rainfall']]
    except Exception as e:
        logger.error(f"Failed to load/melt {rain_csv}: {e}")
        return None

# ==========================================
# Runoff & WB Level Calculation Helpers
# ==========================================
def apply_runoff(df, thresh_path, merge_col, how='left'):
    if thresh_path is None or merge_col is None or 'WaterSupply' not in df.columns: return df
    t_df = pd.read_csv(thresh_path)
    res = pd.merge(df, t_df, on=merge_col, how=how)
    ws = res['WaterSupply']
    conds = [
        (ws <= res['critical_50_level']),
        (ws > res['critical_50_level']) & (ws < res['critical_80_level']),
        (ws >= res['critical_80_level']) & (ws <= res['critical_90_level']),
        (ws > res['critical_90_level'])
    ]
    res['RunoffIndex'] = np.select(conds, [0, 1, 2, 3], default=np.nan)
    res['RunoffIndex'] = res['RunoffIndex'].astype('Int64')
    res.drop(columns=[c for c in t_df.columns if c != merge_col], inplace=True)
    return res

def apply_wb_level(df, thresh_path, merge_col, how='left'):
    if thresh_path is None or merge_col is None or 'WaterBalance' not in df.columns: return df
    t_df = pd.read_csv(thresh_path)
    res = pd.merge(df, t_df, on=merge_col, how=how)
    
    # Safe Extraction of limits
    c0 = res.get('critical_0_level', 0)
    c10 = res.get('critical_10_level', 0)
    c20 = res.get('critical_20_level', 0)
    c30 = res.get('critical_30_level', 0)
    c40 = res.get('critical_40_level', 0)
    c50 = res.get('critical_50_level', 0)
    
    # Check if the thresholds are going positive or negative and normalize them
    # If c50 == c0, direction defaults to 1 to avoid ZeroDivision
    direction = np.where(c50 != c0, np.sign(c50 - c0), 1)
    
    # Multiplying by direction converts everything to a positive-ascending array mathematically
    wb_adj = res['WaterBalance'] * direction
    c0_adj = c0 * direction
    c10_adj = c10 * direction
    c20_adj = c20 * direction
    c30_adj = c30 * direction
    c40_adj = c40 * direction
    c50_adj = c50 * direction
    
    conds = [
        (wb_adj <= c0_adj),
        (wb_adj > c0_adj) & (wb_adj <= c10_adj),
        (wb_adj > c10_adj) & (wb_adj <= c20_adj),
        (wb_adj > c20_adj) & (wb_adj <= c30_adj),
        (wb_adj > c30_adj) & (wb_adj <= c40_adj),
        (wb_adj > c40_adj) & (wb_adj <= c50_adj),
        (wb_adj > c50_adj)
    ]
    
    # Dynamically interpolate exact fraction across the 10-point scale
    choices = [
        0,1,2,3,4,5,6 # Allows slope projection past >50
    ]
    
    res['WB_level'] = np.select(conds, choices, default=np.nan)
    
    drop_cols = ['critical_0_level', 'critical_10_level', 'critical_20_level', 'critical_30_level', 'critical_40_level', 'critical_50_level']
    res.drop(columns=[c for c in drop_cols if c in res.columns], inplace=True)
    return res

def calculate_runoff_index(supply_path, thresholds_path, out_path, f_start, f_end, logger, state_tracker):
    if state_tracker["Water Supply"]["status"] != "SUCCESS": return
    try:
        merged_df = apply_runoff(pd.read_csv(supply_path), thresholds_path, 'Sbswat', how='inner')
        merged_df['Date_Obj'] = pd.to_datetime(merged_df['DateSim'], format='%d/%m/%Y')
        merged_df = merged_df[(merged_df['Date_Obj'] >= pd.to_datetime(f_start)) & (merged_df['Date_Obj'] <= pd.to_datetime(f_end))]
        merged_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'RunoffIndex']].to_csv(out_path, index=False)
        logger.info("Runoff Index -> SUCCESS") 
        update_state(state_tracker, "Runoff Index", "SUCCESS")
    except Exception as e:
        logger.error(f"Runoff Index calculation failed: {e}")
        update_state(state_tracker, "Runoff Index", "FAILED", str(e))

def calculate_wb_level(wb_path, thresholds_path, out_path, f_start, f_end, logger, state_tracker):
    if state_tracker["Water Balance"]["status"] != "SUCCESS": return
    try:
        merged_df = apply_wb_level(pd.read_csv(wb_path), thresholds_path, 'Sbswat', how='inner')
        merged_df['Date_Obj'] = pd.to_datetime(merged_df['DateSim'], format='%d/%m/%Y')
        merged_df = merged_df[(merged_df['Date_Obj'] >= pd.to_datetime(f_start)) & (merged_df['Date_Obj'] <= pd.to_datetime(f_end))]
        merged_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'WB_level']].to_csv(out_path, index=False)
        logger.info("Water Balance Level -> SUCCESS") 
        update_state(state_tracker, "Water Balance Level", "SUCCESS")
    except Exception as e:
        logger.error(f"Water Balance Level calculation failed: {e}")
        update_state(state_tracker, "Water Balance Level", "FAILED", str(e))

# ==========================================
# Hydrological Computation Modules
# ==========================================
def calculate_water_supply(rch_path, out_path, f_start, f_end, logger, state_tracker):
    try:
        df = pd.read_csv(rch_path)
        df['Daily_Vol_MCM'] = (df['FLOW_INcms'] * 86400) / 1_000_000
        df['Date_Obj'] = pd.to_datetime(df['YEAR'].astype(str) + df['DAY'].astype(str).str.zfill(3), format='%Y%j')
        daily_df = df[(df['Date_Obj'] >= pd.to_datetime(f_start)) & (df['Date_Obj'] <= pd.to_datetime(f_end))].copy()
        daily_df['DateSim'] = daily_df['Date_Obj'].dt.strftime('%d/%m/%Y')
        daily_df.rename(columns={'REACH': 'Sbswat', 'Daily_Vol_MCM': 'WaterSupply'}, inplace=True)
        daily_df['WaterSupply'] = daily_df['WaterSupply'].round(3)
        daily_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'WaterSupply']].to_csv(out_path, index=False)
        logger.info("Water Supply (Daily) -> SUCCESS") 
        update_state(state_tracker, "Water Supply", "SUCCESS")
    except Exception as e:
        logger.error(f"Water Supply calculation failed: {e}")
        update_state(state_tracker, "Water Supply", "FAILED", str(e))

def calculate_water_demand(hru_path, wus_path, out_path, f_start, f_end, logger, state_tracker):
    try:
        hru_df, wus_df = pd.read_csv(hru_path), pd.read_csv(wus_path)
        wus_pnd = pd.melt(wus_df, id_vars=['SUBBASIN'], value_vars=[f'WUPND{i}' for i in range(1, 13)], var_name='MON', value_name='WUPND')
        wus_pnd['MON'] = wus_pnd['MON'].str.replace('WUPND', '').astype(int)
        wus_rch = pd.melt(wus_df, id_vars=['SUBBASIN'], value_vars=[f'WURCH{i}' for i in range(1, 13)], var_name='MON', value_name='WURCH')
        wus_rch['MON'] = wus_rch['MON'].str.replace('WURCH', '').astype(int)
        wus_long = pd.merge(wus_pnd, wus_rch, on=['SUBBASIN', 'MON']).fillna(0)
        hru_df['Date_Obj'] = pd.to_datetime(hru_df['YEAR'].astype(str) + hru_df['DAY'].astype(str).str.zfill(3), format='%Y%j')
        hru_df['MON'] = hru_df['Date_Obj'].dt.month
        hru_df['days_in_month'] = hru_df['Date_Obj'].dt.days_in_month
        hru_df['daily_hru_et_mcm'] = (hru_df['ETmm'] * hru_df['AREAkm2']) / 1000.0
        subbasin_daily = hru_df.groupby(['Date_Obj', 'MON', 'days_in_month', 'Sbswat'])['daily_hru_et_mcm'].sum().reset_index()
        merged_df = pd.merge(subbasin_daily, wus_long, left_on=['Sbswat', 'MON'], right_on=['SUBBASIN', 'MON'], how='left').fillna(0)
        merged_df['daily_wus_mcm'] = ((merged_df['WUPND'] + merged_df['WURCH']) / 100.0)
        merged_df['WaterDemand'] = (merged_df['daily_hru_et_mcm'] + merged_df['daily_wus_mcm']).round(3)
        daily_df = merged_df[(merged_df['Date_Obj'] >= pd.to_datetime(f_start)) & (merged_df['Date_Obj'] <= pd.to_datetime(f_end))].copy()
        daily_df['DateSim'] = daily_df['Date_Obj'].dt.strftime('%d/%m/%Y')
        daily_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'WaterDemand']].to_csv(out_path, index=False)
        logger.info("Water Demand (Daily) -> SUCCESS") 
        update_state(state_tracker, "Water Demand", "SUCCESS")
    except Exception as e:
        logger.error(f"Water Demand calculation failed: {e}")
        update_state(state_tracker, "Water Demand", "FAILED", str(e))

def calculate_water_balance(demand_path, supply_path, out_path, logger, state_tracker):
    if state_tracker["Water Demand"]["status"] != "SUCCESS" or state_tracker["Water Supply"]["status"] != "SUCCESS": return
    try:
        merged_df = pd.merge(pd.read_csv(demand_path), pd.read_csv(supply_path), on=['DateSim', 'Sbswat'], how='inner')
        merged_df['WaterBalance'] = (merged_df['WaterSupply'] - merged_df['WaterDemand']).round(3)
        merged_df.sort_values(by=['Sbswat'])[['DateSim', 'Sbswat', 'WaterDemand', 'WaterSupply', 'WaterBalance']].to_csv(out_path, index=False)
        logger.info("Water Balance (Daily) -> SUCCESS") 
        update_state(state_tracker, "Water Balance", "SUCCESS")
    except Exception as e:
        logger.error(f"Water Balance failed: {e}")
        update_state(state_tracker, "Water Balance", "FAILED", str(e))

def calculate_drought_index(hru_path, threshold_path, out_daily, f_start, f_end, logger, state_tracker):
    try:
        hru_df, thresh_df = pd.read_csv(hru_path), pd.read_csv(threshold_path)
        hru_df['LULC'] = hru_df['LULC'].astype(str).str.strip()
        thresh_df['cpnm'] = thresh_df['cpnm'].astype(str).str.strip()
        df = hru_df.merge(thresh_df, left_on='LULC', right_on='cpnm', how='inner')
        df['Date_Obj'] = pd.to_datetime(df['YEAR'].astype(str) + df['DAY'].astype(str).str.zfill(3), format='%Y%j')
        df['wstrs_x_area'] = df['W_STRS'] * df['AREAkm2']

        def process_drought(data, group_cols):
            lulc_agg = data.groupby(group_cols + ['Sbswat', 'LULC']).agg(
                total_wstrs_area=('wstrs_x_area', 'sum'),
                total_area_sum=('AREAkm2', 'sum'),
                sum_period=('sum_period', 'first'),
                min_wtr=('min_wtr_s_days', 'first'),
                max_wtr=('max_wtr_s_days', 'first')
            ).reset_index()

            lulc_agg['avg_w_strs'] = (lulc_agg['total_wstrs_area'] / lulc_agg['total_area_sum']).fillna(0)
            lulc_agg['cum_stress'] = lulc_agg['avg_w_strs'] * lulc_agg['sum_period']
            conditions = [
                (lulc_agg['cum_stress'] <= 0),
                (lulc_agg['cum_stress'] > 0) & (lulc_agg['cum_stress'] <= lulc_agg['min_wtr']),
                (lulc_agg['cum_stress'] > lulc_agg['min_wtr']) & (lulc_agg['cum_stress'] < lulc_agg['max_wtr']),
                (lulc_agg['cum_stress'] >= lulc_agg['max_wtr'])
            ]
            lulc_agg['lulc_drought_index'] = np.select(conditions, [0, 1, 2, 3], default=0)
            lulc_agg['subbasin_total_area_sum'] = lulc_agg.groupby(group_cols + ['Sbswat'])['total_area_sum'].transform('sum')
            lulc_agg['area_weight'] = lulc_agg['total_area_sum'] / lulc_agg['subbasin_total_area_sum']
            lulc_agg['weighted_index'] = lulc_agg['lulc_drought_index'] * lulc_agg['area_weight']
            final_subbasin = lulc_agg.groupby(group_cols + ['Sbswat']).agg(raw_drought_index=('weighted_index', 'sum')).reset_index()
            final_subbasin['DroughtIndex'] = final_subbasin['raw_drought_index'].round().astype(int)
            return final_subbasin

        daily_df = process_drought(df, ['Date_Obj'])
        daily_df = daily_df[(daily_df['Date_Obj'] >= pd.to_datetime(f_start)) & (daily_df['Date_Obj'] <= pd.to_datetime(f_end))].copy()
        daily_df['DateSim'] = daily_df['Date_Obj'].dt.strftime('%d/%m/%Y')
        daily_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'DroughtIndex']].to_csv(out_daily, index=False)

        logger.info("Drought Index (Daily) -> SUCCESS") 
        update_state(state_tracker, "Drought Index", "SUCCESS")
    except Exception as e:
        logger.error(f"Drought Index calculation failed: {e}")
        update_state(state_tracker, "Drought Index", "FAILED", str(e))

def calculate_reservoir(rsv_path, out_path, total_subbasins, res_to_sub_map, f_start, f_end, logger, state_tracker):
    try:
        df = pd.read_csv(rsv_path)
        df['Date_Obj'] = pd.to_datetime(df['YEAR'].astype(str) + df['DAY'].astype(str).str.zfill(3), format='%Y%j')
        df['Reservoir'] = (df['VOLUMEm3'] / 1_000_000).round(3)
        res_data = df[df['RES'].isin(res_to_sub_map.keys())].copy()
        res_data['Sbswat'] = res_data['RES'].map(res_to_sub_map)
        res_data = res_data[['Date_Obj', 'Sbswat', 'Reservoir']]
        
        unique_dates = df['Date_Obj'].unique()
        master_grid = pd.MultiIndex.from_product([unique_dates, np.arange(1, total_subbasins + 1)], names=['Date_Obj', 'Sbswat']).to_frame(index=False)
        final_df = pd.merge(master_grid, res_data, on=['Date_Obj', 'Sbswat'], how='left').fillna(0.0)
        final_df = final_df[(final_df['Date_Obj'] >= pd.to_datetime(f_start)) & (final_df['Date_Obj'] <= pd.to_datetime(f_end))].copy()
        final_df['DateSim'] = final_df['Date_Obj'].dt.strftime('%d/%m/%Y')
        final_df.sort_values(by=['Date_Obj', 'Sbswat'])[['DateSim', 'Sbswat', 'Reservoir']].to_csv(out_path, index=False)
        logger.info("Reservoir Volume (Daily) -> SUCCESS") 
        update_state(state_tracker, "Reservoir", "SUCCESS")
    except Exception as e:
        logger.error(f"Reservoir failed: {e}")
        update_state(state_tracker, "Reservoir", "FAILED", str(e))

def calculate_rainfall(imported_rain_csv, out_path, f_start, f_end, logger, state_tracker):
    try:
        df_rain = load_and_melt_rain_daily(imported_rain_csv, 'Sbswat', f_start, f_end, logger)
        if df_rain is not None:
            df_rain['temp_date'] = pd.to_datetime(df_rain['DateSim'], format='%d/%m/%Y')
            df_rain = df_rain.sort_values(by=['temp_date', 'Sbswat']).drop(columns=['temp_date'])
            df_rain.to_csv(out_path, index=False)
            logger.info("Rainfall Formatting (Daily) -> SUCCESS")
            update_state(state_tracker, "Rain", "SUCCESS")
        else: raise FileNotFoundError(f"Missing data in {imported_rain_csv}")
    except Exception as e:
        logger.error(f"Rainfall formatting failed: {e}")
        update_state(state_tracker, "Rain", "FAILED", str(e))

# ==========================================
# Integration and Aggregation
# ==========================================     
def integrate_results(paths, out_path, mb_code, mb_name_t, logger):
    try:
        merged = pd.read_csv(paths['wb']).merge(pd.read_csv(paths['rain']), on=['DateSim', 'Sbswat'], how='outer')
        
        # Merge the rest, including the new wb_level output
        for p in ['drought', 'runoff', 'wb_level', 'reservoir']:
            if os.path.exists(paths[p]):
                merged = pd.merge(merged, pd.read_csv(paths[p]), on=['DateSim', 'Sbswat'], how='left')
            
        merged['Reservoir'] = merged.get('Reservoir', pd.Series(0.0, index=merged.index)).fillna(0.0)
        merged['MB_CODE'], merged['MB_NAME_T'] = mb_code, mb_name_t
        
        cols = [c for c in ['DateSim', 'Sbswat', 'MB_CODE', 'MB_NAME_T', 'Rainfall', 'Reservoir', 'WaterSupply', 'WaterDemand', 'WaterBalance', 'DroughtIndex', 'RunoffIndex', 'WB_level'] if c in merged.columns]
        merged = merged[cols]
        merged['temp_date'] = pd.to_datetime(merged['DateSim'], format='%d/%m/%Y')
        merged.sort_values(by=['temp_date', 'Sbswat']).drop(columns=['temp_date']).to_csv(out_path, index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        logger.error(f"Integration failed: {e}")
        return False

def aggregate_daily_to_weekly_summary(daily_csv_path, output_dir, prefix, id_cols, f_start, logger, thresh_runoff_path=None, thresh_wb_path=None, merge_col=None):
    try:
        df = pd.read_csv(daily_csv_path)
        df['temp_date'] = pd.to_datetime(df['DateSim'], format='%d/%m/%Y')
        f_start_dt = pd.to_datetime(f_start)
        df['days_since_start'] = (df['temp_date'] - f_start_dt).dt.days
        df['week_start_date'] = f_start_dt + pd.to_timedelta((df['days_since_start'] // 7) * 7, unit='D')
        df['DateSim_Weekly'] = df['week_start_date'].dt.strftime('%d/%m/%Y')
        
        rules = {col: 'sum' for col in ['WaterSupply', 'WaterDemand', 'WaterBalance', 'Reservoir', 'Rainfall'] if col in df.columns}
        if 'DroughtIndex' in df.columns: rules['DroughtIndex'] = get_mode_or_mean

        weekly_df = df.groupby(['DateSim_Weekly'] + id_cols, as_index=False).agg(rules).rename(columns={'DateSim_Weekly': 'DateSim'})
        
        weekly_df = apply_runoff(weekly_df, thresh_runoff_path, merge_col, how='left')
        weekly_df = apply_wb_level(weekly_df, thresh_wb_path, merge_col, how='left')

        for col in ['DroughtIndex', 'RunoffIndex']:
            if col in weekly_df.columns: 
                weekly_df[col] = pd.to_numeric(weekly_df[col], errors='coerce').round().astype('Int64')
        
        weekly_df.sort_values(by=['DateSim'] + [id_cols[0]]).to_csv(output_dir / f"{prefix}_Weekly.csv", index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        logger.error(f"Failed to generate weekly summary for {prefix}: {e}")
        return False

def aggregate_daily_to_monthly_summary(daily_csv_path, output_dir, prefix, id_cols, logger, thresh_runoff_path=None, thresh_wb_path=None, merge_col=None):
    try:
        df = pd.read_csv(daily_csv_path)
        df['temp_date'] = pd.to_datetime(df['DateSim'], format='%d/%m/%Y')
        df['YEAR'] = df['temp_date'].dt.year
        df['MON'] = df['temp_date'].dt.month
        
        rules = {col: 'sum' for col in ['WaterSupply', 'WaterDemand', 'WaterBalance', 'Reservoir', 'Rainfall'] if col in df.columns}
        if 'DroughtIndex' in df.columns: rules['DroughtIndex'] = get_mode_or_mean

        monthly_df = df.groupby(['YEAR', 'MON'] + id_cols, as_index=False).agg(rules)
        
        monthly_df = apply_runoff(monthly_df, thresh_runoff_path, merge_col, how='left')
        monthly_df = apply_wb_level(monthly_df, thresh_wb_path, merge_col, how='left')
        
        for col in ['DroughtIndex', 'RunoffIndex']:
            if col in monthly_df.columns: 
                monthly_df[col] = pd.to_numeric(monthly_df[col], errors='coerce').round().astype('Int64')
        
        monthly_df.sort_values(by=['YEAR', 'MON'] + [id_cols[0]]).to_csv(output_dir / f"{prefix}_Monthly.csv", index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        logger.error(f"Failed to generate monthly summary for {prefix}: {e}")
        return False

def aggregate_admin(base_path, frac_path, out_dir, inputs, f_start, f_end, logger, state_tracker):
    try:
        df_merged = pd.merge(pd.read_csv(base_path), pd.read_csv(frac_path), on='Sbswat', how='inner')
        for col in ['WaterSupply', 'WaterDemand', 'WaterBalance']:
            if col in df_merged.columns: df_merged[col] *= df_merged['per_sbswat']
        for col in ['Reservoir', 'DroughtIndex']:
            if col in df_merged.columns: df_merged[col] *= df_merged['per_tambol']

        # --- Tambol ---
        group_cols = ['DateSim', 'Tambol_ID', 'Tambol', 'Amphoe_ID', 'Amphoe', 'Province_ID', 'Province']
        agg_cols = [c for c in ['Reservoir', 'WaterSupply', 'WaterDemand', 'WaterBalance', 'DroughtIndex'] if c in df_merged.columns]
        df_tambol = df_merged.groupby(group_cols, as_index=False)[agg_cols].sum()
        
        r_tambol = load_and_melt_rain_daily(inputs['rain_tambol_imported'], "Tambol_ID", f_start, f_end, logger)
        if r_tambol is not None: df_tambol = pd.merge(df_tambol, r_tambol, on=['DateSim', 'Tambol_ID'], how='left')

        df_tambol = apply_runoff(df_tambol, inputs['thresh_tambol_day'], 'Tambol_ID')
        df_tambol = apply_wb_level(df_tambol, inputs['thresh_wb_tambol_day'], 'Tambol_ID')
        
        if 'DroughtIndex' in df_tambol.columns: df_tambol['DroughtIndex'] = df_tambol['DroughtIndex'].round().astype('Int64')
        df_tambol['temp_date'] = pd.to_datetime(df_tambol['DateSim'], format='%d/%m/%Y')
        df_tambol.sort_values(by=['temp_date', 'Province_ID', 'Amphoe_ID', 'Tambol_ID']).drop(columns=['temp_date']).to_csv(out_dir / "Tambol_Daily.csv", index=False, encoding='utf-8-sig')
        
        if SWAT_MODE == "month":
            aggregate_daily_to_monthly_summary(out_dir / "Tambol_Daily.csv", out_dir, "Tambol", ['Tambol_ID', 'Tambol', 'Amphoe_ID', 'Amphoe', 'Province_ID', 'Province'], logger, inputs['thresh_tambol_month'], inputs['thresh_wb_tambol_month'], 'Tambol_ID')
        else:
            aggregate_daily_to_weekly_summary(out_dir / "Tambol_Daily.csv", out_dir, "Tambol", ['Tambol_ID', 'Tambol', 'Amphoe_ID', 'Amphoe', 'Province_ID', 'Province'], f_start, logger, inputs['thresh_tambol_week'], inputs['thresh_wb_tambol_week'], 'Tambol_ID')

        # --- Amphoe ---
        a_group = ['DateSim', 'Amphoe_ID', 'Amphoe', 'Province_ID', 'Province']
        rules = {k: v for k, v in {'Reservoir':'sum', 'WaterSupply':'sum', 'WaterDemand':'sum', 'WaterBalance':'sum', 'DroughtIndex':get_mode_or_mean}.items() if k in df_tambol.columns}
        df_amphoe = df_tambol.groupby(a_group, as_index=False).agg(rules)
        
        r_amphoe = load_and_melt_rain_daily(inputs['rain_amphoe_imported'], "Amphoe_ID", f_start, f_end, logger)
        if r_amphoe is not None: df_amphoe = pd.merge(df_amphoe, r_amphoe, on=['DateSim', 'Amphoe_ID'], how='left')

        df_amphoe = apply_runoff(df_amphoe, inputs['thresh_amphoe_day'], 'Amphoe_ID')
        df_amphoe = apply_wb_level(df_amphoe, inputs['thresh_wb_amphoe_day'], 'Amphoe_ID')
        
        if 'DroughtIndex' in df_amphoe.columns: df_amphoe['DroughtIndex'] = df_amphoe['DroughtIndex'].round().astype('Int64')
        df_amphoe['temp_date'] = pd.to_datetime(df_amphoe['DateSim'], format='%d/%m/%Y')
        df_amphoe.sort_values(by=['temp_date', 'Province_ID', 'Amphoe_ID']).drop(columns=['temp_date']).to_csv(out_dir / "Amphoe_Daily.csv", index=False, encoding='utf-8-sig')
        
        if SWAT_MODE == "month":
            aggregate_daily_to_monthly_summary(out_dir / "Amphoe_Daily.csv", out_dir, "Amphoe", ['Amphoe_ID', 'Amphoe', 'Province_ID', 'Province'], logger, inputs['thresh_amphoe_month'], inputs['thresh_wb_amphoe_month'], 'Amphoe_ID')
        else:
            aggregate_daily_to_weekly_summary(out_dir / "Amphoe_Daily.csv", out_dir, "Amphoe", ['Amphoe_ID', 'Amphoe', 'Province_ID', 'Province'], f_start, logger, inputs['thresh_amphoe_week'], inputs['thresh_wb_amphoe_week'], 'Amphoe_ID')

        # --- Province ---
        p_group = ['DateSim', 'Province_ID', 'Province']
        df_prov = df_amphoe.groupby(p_group, as_index=False).agg(rules)
        
        r_prov = load_and_melt_rain_daily(inputs['rain_province_imported'], "Province_ID", f_start, f_end, logger)
        if r_prov is not None: df_prov = pd.merge(df_prov, r_prov, on=['DateSim', 'Province_ID'], how='left')

        df_prov = apply_runoff(df_prov, inputs['thresh_province_day'], 'Province_ID')
        df_prov = apply_wb_level(df_prov, inputs['thresh_wb_province_day'], 'Province_ID')
        
        if 'DroughtIndex' in df_prov.columns: df_prov['DroughtIndex'] = df_prov['DroughtIndex'].round().astype('Int64')
        df_prov['temp_date'] = pd.to_datetime(df_prov['DateSim'], format='%d/%m/%Y')
        df_prov.sort_values(by=['temp_date', 'Province_ID']).drop(columns=['temp_date']).to_csv(out_dir / "Province_Daily.csv", index=False, encoding='utf-8-sig')
        
        if SWAT_MODE == "month":
            aggregate_daily_to_monthly_summary(out_dir / "Province_Daily.csv", out_dir, "Province", ['Province_ID', 'Province'], logger, inputs['thresh_province_month'], inputs['thresh_wb_province_month'], 'Province_ID')
        else:
            aggregate_daily_to_weekly_summary(out_dir / "Province_Daily.csv", out_dir, "Province", ['Province_ID', 'Province'], f_start, logger, inputs['thresh_province_week'], inputs['thresh_wb_province_week'], 'Province_ID')

        logger.info("Admin Aggregation -> SUCCESS")
        update_state(state_tracker, "Administrative Units", "SUCCESS")
    except Exception as e:
        logger.error(f"Admin Aggregation failed: {e}")
        update_state(state_tracker, "Administrative Units", "FAILED", str(e))

def aggregate_onwr(base_path, frac_path, out_dir, inputs, f_start, f_end, logger, state_tracker):
    try:
        df_base, df_frac = pd.read_csv(base_path), pd.read_csv(frac_path)
        for df in [df_base, df_frac]:
            if 'MB_CODE' in df.columns: df['MB_CODE'] = pd.to_numeric(df['MB_CODE'], errors='coerce')
        df_merged = pd.merge(df_base, df_frac, on=['Sbswat', 'MB_CODE'], how='inner')
        
        t_cols = ['Reservoir', 'WaterSupply', 'WaterDemand', 'WaterBalance', 'DroughtIndex']
        for col in t_cols:
            if col in df_merged.columns:
                if df_merged[col].dtype == 'object': df_merged[col] = df_merged[col].astype(str).str.replace(',', '', regex=False)
                df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce') * df_merged['fraction']

        # --- SBONWR ---
        group_sb = ['DateSim', 'SB_CODE', 'SB_NAME_T', 'MB_CODE', 'MB_NAME_T']
        df_sb = df_merged.groupby(group_sb, as_index=False)[[c for c in t_cols if c in df_merged.columns]].sum(min_count=1)
        r_sb = load_and_melt_rain_daily(inputs['rain_sbonwr_imported'], "SB_CODE", f_start, f_end, logger)
        if r_sb is not None: df_sb = pd.merge(df_sb, r_sb, on=['DateSim', 'SB_CODE'], how='left')

        df_sb = apply_runoff(df_sb, inputs['thresh_sb_day'], 'SB_CODE')
        df_sb = apply_wb_level(df_sb, inputs['thresh_wb_sb_day'], 'SB_CODE')
        
        if 'DroughtIndex' in df_sb.columns: df_sb['DroughtIndex'] = df_sb['DroughtIndex'].round().astype('Int64')
        df_sb['temp_date'] = pd.to_datetime(df_sb['DateSim'], format='%d/%m/%Y')
        df_sb = df_sb.sort_values(by=['temp_date', 'MB_CODE', 'SB_CODE']).drop(columns=['temp_date'])
        df_sb.to_csv(out_dir / "Sbonwr_Daily.csv", index=False, encoding='utf-8-sig')
        
        if SWAT_MODE == "month":
            aggregate_daily_to_monthly_summary(out_dir / "Sbonwr_Daily.csv", out_dir, "Sbonwr", ['SB_CODE', 'SB_NAME_T', 'MB_CODE', 'MB_NAME_T'], logger, inputs['thresh_sb_month'], inputs['thresh_wb_sb_month'], 'SB_CODE')
        else:
            aggregate_daily_to_weekly_summary(out_dir / "Sbonwr_Daily.csv", out_dir, "Sbonwr", ['SB_CODE', 'SB_NAME_T', 'MB_CODE', 'MB_NAME_T'], f_start, logger, inputs['thresh_sb_week'], inputs['thresh_wb_sb_week'], 'SB_CODE')

        # --- MB_CODE ---
        group_mb = ['DateSim', 'MB_CODE', 'MB_NAME_T']
        rules = {k: v for k, v in {'Reservoir':'sum', 'WaterSupply':'sum', 'WaterDemand':'sum', 'WaterBalance':'sum', 'DroughtIndex':get_mode_or_mean}.items() if k in df_sb.columns}
        df_mb = df_sb.groupby(group_mb, as_index=False).agg(rules)
        r_mb = load_and_melt_rain_daily(inputs['rain_bonwr_imported'], "MB_CODE", f_start, f_end, logger)
        if r_mb is not None: df_mb = pd.merge(df_mb, r_mb, on=['DateSim', 'MB_CODE'], how='left')

        df_mb = apply_runoff(df_mb, inputs['thresh_mb_day'], 'MB_CODE')
        df_mb = apply_wb_level(df_mb, inputs['thresh_wb_mb_day'], 'MB_CODE')
        
        if 'DroughtIndex' in df_mb.columns: df_mb['DroughtIndex'] = pd.to_numeric(df_mb['DroughtIndex'], errors='coerce').round().astype('Int64')
        df_mb['temp_date'] = pd.to_datetime(df_mb['DateSim'], format='%d/%m/%Y')
        df_mb = df_mb.sort_values(by=['temp_date', 'MB_CODE']).drop(columns=['temp_date'])
        df_mb.to_csv(out_dir / "Bonwr_Daily.csv", index=False, encoding='utf-8-sig')
        
        if SWAT_MODE == "month":
            aggregate_daily_to_monthly_summary(out_dir / "Bonwr_Daily.csv", out_dir, "Bonwr", ['MB_CODE', 'MB_NAME_T'], logger, inputs['thresh_mb_month'], inputs['thresh_wb_mb_month'], 'MB_CODE')
        else:
            aggregate_daily_to_weekly_summary(out_dir / "Bonwr_Daily.csv", out_dir, "Bonwr", ['MB_CODE', 'MB_NAME_T'], f_start, logger, inputs['thresh_mb_week'], inputs['thresh_wb_mb_week'], 'MB_CODE')

        logger.info("ONWR Aggregation -> SUCCESS")
        update_state(state_tracker, "ONWR Units", "SUCCESS")
    except Exception as e:
        logger.error(f"ONWR Aggregation failed: {e}")
        update_state(state_tracker, "ONWR Units", "FAILED", str(e))

def run_swat_analysis(txtinout_dir, output_dir, inputs, config, alert_dir, logger):
    logger.info(f"Analysis started in [{SWAT_MODE.upper()}] mode")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pipeline_failed = False
    state_tracker = {
        "Water Supply": {"status": "NOT EXECUTED", "error": None},
        "Water Demand": {"status": "NOT EXECUTED", "error": None},
        "Water Balance": {"status": "NOT EXECUTED", "error": None},
        "Runoff Index": {"status": "NOT EXECUTED", "error": None},
        "Water Balance Level": {"status": "NOT EXECUTED", "error": None},
        "Drought Index": {"status": "NOT EXECUTED", "error": None},
        "Reservoir": {"status": "NOT EXECUTED", "error": None},
        "Rain": {"status": "NOT EXECUTED", "error": None},
        "Administrative Units": {"status": "NOT EXECUTED", "error": None},
        "ONWR Units": {"status": "NOT EXECUTED", "error": None}
    }
    
    f_start, f_end = config['forecast_start'], config['forecast_end']

    if load_outputs(txtinout_dir, output_dir, config['actual_print_start_year']):
        rch_csv, hru_csv, rsv_csv = output_dir/"rch.csv", output_dir/"hru.csv", output_dir/"rsv.csv"
        
        calculate_water_supply(rch_csv, inputs['water_supply'], f_start, f_end, logger, state_tracker)
        calculate_water_demand(hru_csv, inputs['wus_raw'], inputs['water_demand'], f_start, f_end, logger, state_tracker)
        calculate_water_balance(inputs['water_demand'], inputs['water_supply'], inputs['water_balance'], logger, state_tracker)
        
        calculate_runoff_index(inputs['water_supply'], inputs['thresh_sbswat_day'], inputs['runoff_idx'], f_start, f_end, logger, state_tracker)
        calculate_wb_level(inputs['water_balance'], inputs['thresh_wb_sbswat_day'], inputs['wb_level_idx'], f_start, f_end, logger, state_tracker)
        
        calculate_drought_index(hru_csv, inputs['thresh_drought'], inputs['drought_idx'], f_start, f_end, logger, state_tracker)
        calculate_reservoir(rsv_csv, inputs['reservoir_idx'], config['total_subbasins'], config['res_to_sub_map'], f_start, f_end, logger, state_tracker)
        calculate_rainfall(inputs['rain_raw_imported'], inputs['rainfall_idx'], f_start, f_end, logger, state_tracker)

        int_paths = {'wb': inputs['water_balance'], 'rain': inputs['rainfall_idx'], 'drought': inputs['drought_idx'], 'runoff': inputs['runoff_idx'], 'wb_level': inputs['wb_level_idx'], 'reservoir': inputs['reservoir_idx']}
        
        integration_success = False
        if integrate_results(int_paths, inputs['analysis_base'], config['mb_code'], config['mb_name_t'], logger):
            if state_tracker["Water Supply"]["status"] == "SUCCESS":
                
                if SWAT_MODE == "month":
                    aggregate_daily_to_monthly_summary(inputs['analysis_base'], output_dir, "Analysis_Sbswat", ['Sbswat', 'MB_CODE', 'MB_NAME_T'], logger, inputs['thresh_sbswat_month'], inputs['thresh_wb_sbswat_month'], 'Sbswat')
                else:
                    aggregate_daily_to_weekly_summary(inputs['analysis_base'], output_dir, "Analysis_Sbswat", ['Sbswat', 'MB_CODE', 'MB_NAME_T'], f_start, logger, inputs['thresh_sbswat_week'], inputs['thresh_wb_sbswat_week'], 'Sbswat')
                
                aggregate_admin(inputs['analysis_base'], inputs['frac_admin'], output_dir, inputs, f_start, f_end, logger, state_tracker)
                aggregate_onwr(inputs['analysis_base'], inputs['frac_onwr'], output_dir, inputs, f_start, f_end, logger, state_tracker)
                integration_success = True
            else:
                logger.error("Integration Failed. Aggregations skipped.")
        else:
            pipeline_failed = True
    
    if any(v["status"] == "FAILED" for v in state_tracker.values()) or pipeline_failed or not integration_success:
        logger.error("Analysis Process: FAILED")
    else:
        logger.info("Analysis Process: SUCCESS")
        
    generate_email_alert(state_tracker, os.path.join(alert_dir, "email_alert_simulation.txt"), phase_name="Analysis Process")
    return state_tracker, pipeline_failed
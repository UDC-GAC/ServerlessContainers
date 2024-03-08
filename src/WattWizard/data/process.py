import warnings
import pandas as pd
from datetime import datetime, timedelta

from src.WattWizard.config import config
from src.WattWizard.logs.logger import log
from src.WattWizard.influxdb.influxdb_queries import var_query
from src.WattWizard.influxdb.influxdb import query_influxdb

current_vars = []
OUT_RANGE = 1.5

warnings.simplefilter(action='ignore', category=FutureWarning)


def get_timestamp_from_line(start_line, stop_line, offset):
    start_str = " ".join(start_line.split(" ")[-2:]).strip()
    stop_str = " ".join(stop_line.split(" ")[-2:]).strip()
    exp_type = start_line.split(" ")[1]
    if exp_type == "IDLE":
        offset = 0
    start = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S%z') + timedelta(seconds=offset)
    stop = datetime.strptime(stop_str, '%Y-%m-%d %H:%M:%S%z') - timedelta(seconds=offset)
    return [(start, stop, exp_type)]


def parse_timestamps(file):
    try:
        with open(file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        log(f"Error while parsing timestamps (file doesn't exists): {file}", "ERR")
    timestamps = []
    for i in range(0, len(lines), 2):
        start_line = lines[i]
        stop_line = lines[i + 1]
        ts_line = get_timestamp_from_line(start_line, stop_line, 20)
        timestamps.append(ts_line[0])
    log(f"Timestamps belong to period [{timestamps[0][0]}, {timestamps[-1][1]}]")
    return timestamps


# Remove outliers for a specified column
def remove_outliers(df, column):
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - OUT_RANGE * iqr
    upper_bound = q3 + OUT_RANGE * iqr
    df_filtered = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]
    return df_filtered


# Get data for a given period (obtained from timestamps)
def get_experiment_data(timestamp):
    global current_vars
    start_date, stop_date, exp_type = timestamp
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_str = stop_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get current_vars time series and merge data
    exp_data = pd.DataFrame()
    for var in current_vars:
        df = query_influxdb(var_query[var], start_str, stop_str, config.influxdb_bucket)
        if not df.empty:
            df = remove_outliers(df, "_value")
            df.rename(columns={'_value': var}, inplace=True)
            df = df[["_time", var]]
            if exp_data.empty:
                exp_data = df
            else:
                exp_data = pd.merge(exp_data, df, on='_time')
    exp_data.rename(columns={'_time': 'time'}, inplace=True)

    # Remove DataFrame useless variables
    try:
        exp_data = exp_data[current_vars + ["time"]]
    except KeyError:
        log(f"Error getting data between {start_date} and {stop_date}", "ERR")
        print(exp_data)
        exit(1)
    return exp_data


# Get _vars time series from timestamps
def get_time_series(_vars, timestamps, include_idle=False):
    global current_vars
    current_vars = _vars.copy()
    time_series = pd.DataFrame(columns=current_vars)

    # Remove idle periods when include_idle is false
    filtered_timestamps = [t for t in timestamps if include_idle or t[2] != "IDLE"]

    for timestamp in filtered_timestamps:
        result = get_experiment_data(timestamp)
        result.dropna(inplace=True)
        time_series = pd.concat([time_series, result], ignore_index=True)

    return time_series


def get_idle_consumption(timestamps):
    # Get power only from idle periods
    filtered_timestamps = [t for t in timestamps if t[2] == "IDLE"]
    time_series = get_time_series(["power"], filtered_timestamps, include_idle=True)
    return time_series["power"].mean()
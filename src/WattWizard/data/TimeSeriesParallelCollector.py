import warnings
import pandas as pd
import concurrent.futures
import multiprocessing
from datetime import datetime, timedelta, timezone

from src.WattWizard.logs.logger import log
from src.WattWizard.influxdb.InfluxDBCollector import InfluxDBHandler

OUT_RANGE = 1.5
MAX_CPU_USAGE_RATIO = 1.0  # Use up to MAX_CPU_USAGE_RATIO of total CPU cores to retrieve InfluxDB time series
START_OFFSET = 20  # Offset to start timestamp
STOP_OFFSET = 10  # Offset to stop timestamp
MIN_PERIOD_LENGTH = START_OFFSET + STOP_OFFSET + 10  # Period should have at least 10 seconds substracting offsets

warnings.simplefilter(action='ignore', category=FutureWarning)


class TimeSeriesParallelCollector:

    max_cores = None
    model_variables = None
    influxdb_info = None
    structure = None

    def __init__(self, model_variables, influxdb_host, influxdb_bucket, influxdb_token, influxdb_org):
        self.max_cores = round(multiprocessing.cpu_count() * MAX_CPU_USAGE_RATIO)
        self.power_variables = ["power_pkg0", "power_pkg1"]
        self._set_model_variables(model_variables)
        self.influxdb_info = {
            "host": influxdb_host,
            "bucket": influxdb_bucket,
            "token": influxdb_token,
            "org": influxdb_org
        }

    def _set_model_variables(self, v):
        if not v:
            raise Exception(f"Trying to set model variables from {self.__class__.__name__} with a bad value '{v}'")
        self.model_variables = v

    # Remove outliers for a specified column
    @staticmethod
    def remove_outliers(df, column):
        q1 = df[column].quantile(0.25)
        q3 = df[column].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - OUT_RANGE * iqr
        upper_bound = q3 + OUT_RANGE * iqr
        df_filtered = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]
        return df_filtered

    @staticmethod
    def get_timestamp_from_line(start_line, stop_line):
        exp_name = start_line.split(" ")[0]
        exp_type = start_line.split(" ")[1]
        cores = start_line.split(" ")[4].strip(')')
        start_offset = 0 if exp_type == "IDLE" else START_OFFSET
        stop_offset = 0 if exp_type == "IDLE" else STOP_OFFSET
        start_str = " ".join(start_line.split(" ")[-2:]).strip()
        stop_str = " ".join(stop_line.split(" ")[-2:]).strip()
        start = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S%z') + timedelta(seconds=start_offset)
        stop = datetime.strptime(stop_str, '%Y-%m-%d %H:%M:%S%z') - timedelta(seconds=stop_offset)
        return start, stop, exp_name, exp_type, cores

    @staticmethod
    def parse_timestamps(file):
        try:
            with open(file, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            log(f"Error while parsing timestamps (file doesn't exists): {file}", "ERR")

        timestamps = []
        total_lines = len(lines)
        if total_lines % 2 != 0:
            total_lines -= 1
        for i in range(0, total_lines, 2):
            start_line = lines[i]
            stop_line = lines[i + 1]
            ts_line = TimeSeriesParallelCollector.get_timestamp_from_line(start_line, stop_line)
            timestamps.append(ts_line)
        log(f"First and last timestamps are [{timestamps[0][0]}, {timestamps[-1][1]}]")
        return timestamps

    @staticmethod
    def join_timestamps(timestamps):
        exp_name, exp_type, cores = None, None, None
        first_start = datetime.max.replace(tzinfo=timezone.utc)
        last_stop = datetime.min.replace(tzinfo=timezone.utc)
        for ts in timestamps:
            if ts[0] < first_start:
                first_start, exp_name, exp_type, cores = ts[0], ts[2], ts[3], ts[4]
            if ts[1] > last_stop:
                last_stop = ts[1]
        return [(first_start, last_stop, exp_name, exp_type, cores)]

    @staticmethod
    def filter_timestamps_by_period_length(timestamps):
        return [ts for ts in timestamps if (ts[1] - ts[0]).total_seconds() >= MIN_PERIOD_LENGTH]

    # Add time_diff column which represents time instead of dates
    @staticmethod
    def set_time_diff(df, time_column, initial_date=None):
        first_date = initial_date if initial_date is not None else df[time_column].min()
        last_date = df[time_column].max()
        time_diff = (df[time_column] - first_date)
        total_duration = last_date - first_date

        # Depending on time series duration different time units are used
        if total_duration < pd.Timedelta(hours=1):
            df["time_diff"] = time_diff.dt.total_seconds()
            df["time_unit"] = 'seconds'
        elif total_duration < pd.Timedelta(hours=12):
            df["time_diff"] = time_diff.dt.total_seconds() / 60
            df["time_unit"] = 'minutes'
        else:
            df["time_diff"] = time_diff.dt.total_seconds() / 3600
            df["time_unit"] = 'hours'

    # Get data for a given period (obtained from timestamps)
    def get_experiment_data(self, structure, metrics, timestamp, influxdb_info):
        start_date, stop_date, exp_name, exp_type, cores = timestamp
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_str = stop_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        with InfluxDBHandler(influxdb_info["host"], influxdb_info["bucket"],
                             influxdb_info["token"], influxdb_info["org"]) as conn:
            # Get model variables time series and merge data
            exp_data = pd.DataFrame()
            for metric in metrics:

                df = conn.query_influxdb(metric, structure, start_str, stop_str)

                if not df.empty:
                    df = self.remove_outliers(df, "_value")
                    df.rename(columns={'_value': metric}, inplace=True)
                    df = df.loc[:, ("_time", metric)]
                    if exp_data.empty:
                        exp_data = df
                    else:
                        exp_data = pd.merge(exp_data, df, on='_time')
        exp_data.rename(columns={'_time': 'time'}, inplace=True)
        exp_data.loc[:, "exp_name"] = exp_name
        exp_data.loc[:, "exp_type"] = exp_type
        exp_data.loc[:, "cores"] = cores

        # Remove DataFrame useless variables
        try:
            exp_data["power"] = exp_data.loc[:, "power_pkg0"] + exp_data.get("power_pkg1", 0)
            exp_data = exp_data[metrics + ["power", "exp_name", "exp_type", "cores", "time"]]
        except KeyError as e:
            log(f"Error getting data between {start_date} and {stop_date}: {str(e)}", "ERR")
            log(f"Data causing the error: {exp_data}", "ERR")
            exit(1)
        return exp_data

    def _filter_timestamps_and_metrics(self, timestamps, mode):
        # only_idle: Include only time series corresponding to idle periods, don't include model variables as metrics
        if mode == "only_idle":
            return [t for t in timestamps if t[3] == "IDLE"], self.power_variables
        # no_idle: Include only time series corresponding to active periods, include all metrics
        if mode == "no_idle":
            return [t for t in timestamps if t[3] != "IDLE"], self.model_variables + self.power_variables
        # all: Include all time series and all metrics
        if mode == "all":
            return timestamps, self.model_variables + self.power_variables

        raise ValueError(f"Unknown mode {mode} when trying to get time series in {self.__class__.__name__}")

    # Get model variables time series from timestamps
    def get_time_series(self, structure, timestamps, mode="all", join=False):
        # Filter timestamps and metrics to get from InfluxDB according to mode
        filtered_timestamps, metrics = self._filter_timestamps_and_metrics(timestamps, mode)

        if len(filtered_timestamps) == 0:
            log(f"Timestamps not valid to get time series in mode '{mode}'", "ERR")
            log("Timestamps must follow the format: <EXP_NAME> <EXP_TYPE> ... <START|STOP> <TIMESTAMP>", "ERR")
            return None

        # Join all timestamps taking the earliest and the oldest timestamps if specified
        if join:
            filtered_timestamps = self.join_timestamps(filtered_timestamps)

        # Ensure all the timestamps have a minimum period length
        filtered_timestamps = self.filter_timestamps_by_period_length(filtered_timestamps)
        if not filtered_timestamps:
            log(f"Timestamps not valid, they must have a minimum period length of {MIN_PERIOD_LENGTH} seconds. "
                f"Try using --join-<train|test>-timestamps option.", "ERR")
            return None

        result_dfs = []
        workers = min(len(timestamps), self.max_cores)
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            thread_to_timestamp = {
                executor.submit(self.get_experiment_data, structure, metrics, ts, self.influxdb_info): ts for ts in filtered_timestamps}
            for thread in concurrent.futures.as_completed(thread_to_timestamp):
                result_dfs.append(thread.result())

        time_series = pd.concat(result_dfs, ignore_index=True)
        self.set_time_diff(time_series, "time")

        return time_series

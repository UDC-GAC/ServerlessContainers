import warnings
import pandas as pd
from datetime import datetime, timedelta

from src.WattWizard.logs.logger import log
from src.WattWizard.influxdb.InfluxDBCollector import InfluxDBCollector

OUT_RANGE = 1.5
START_OFFSET = 30  # Offset to start timestamp
STOP_OFFSET = 10  # Offset to stop timestamp
warnings.simplefilter(action='ignore', category=FutureWarning)


class TimeSeriesCollector:

    model_variables = None
    influxdb_handler = None
    structure = None

    def __init__(self, model_variables, influxdb_host, influxdb_bucket, influxdb_token, influxdb_org):
        self.model_variables = model_variables
        self.influxdb_handler = InfluxDBCollector(influxdb_host, influxdb_bucket, influxdb_token, influxdb_org)

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
        start_offset = 0 if exp_type == "IDLE" else START_OFFSET
        stop_offset = 0 if exp_type == "IDLE" else STOP_OFFSET
        start_str = " ".join(start_line.split(" ")[-2:]).strip()
        stop_str = " ".join(stop_line.split(" ")[-2:]).strip()
        start = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S%z') + timedelta(seconds=start_offset)
        stop = datetime.strptime(stop_str, '%Y-%m-%d %H:%M:%S%z') - timedelta(seconds=stop_offset)
        return start, stop, exp_name, exp_type

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

    def __set_model_variables(self, v):
        if v is not None:
            self.model_variables = v
        raise Exception("Trying to set model variables from TimeSeriesCollector as None")

    def set_structure(self, structure):
        self.structure = structure

    def parse_timestamps(self, file):
        try:
            with open(file, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            log(f"Error while parsing timestamps (file doesn't exists): {file}", "ERR")
        timestamps = []
        for i in range(0, len(lines), 2):
            start_line = lines[i]
            stop_line = lines[i + 1]
            ts_line = self.get_timestamp_from_line(start_line, stop_line)
            timestamps.append(ts_line)
        log(f"Timestamps belong to period [{timestamps[0][0]}, {timestamps[-1][1]}]")
        return timestamps

    # Get data for a given period (obtained from timestamps)
    def get_experiment_data(self, timestamp):
        start_date, stop_date, exp_name, exp_type = timestamp
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_str = stop_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Get model variables time series and merge data
        exp_data = pd.DataFrame()
        for var in self.model_variables:
            df = self.influxdb_handler.query_influxdb(var, self.structure, start_str, stop_str)
            if not df.empty:
                df = self.remove_outliers(df, "_value")
                df.rename(columns={'_value': var}, inplace=True)
                df = df[["_time", var]]
                if exp_data.empty:
                    exp_data = df
                else:
                    exp_data = pd.merge(exp_data, df, on='_time')
        exp_data.rename(columns={'_time': 'time'}, inplace=True)

        # Remove DataFrame useless variables
        try:
            exp_data = exp_data[self.model_variables + ["time"]]
            exp_data["exp_name"] = exp_name
            exp_data["exp_type"] = exp_type
        except KeyError as e:
            log(f"Error getting data between {start_date} and {stop_date}: {str(e)}", "ERR")
            log(f"Data causing the error: {exp_data}", "ERR")
            exit(1)
        return exp_data

    # Get model variables time series from timestamps
    def get_time_series(self, timestamps, include_idle=False):
        time_series = pd.DataFrame(columns=self.model_variables)

        # Remove idle periods when include_idle is False
        filtered_timestamps = [t for t in timestamps if include_idle or t[3] != "IDLE"]

        for timestamp in filtered_timestamps:
            result = self.get_experiment_data(timestamp)
            result.dropna(inplace=True)
            time_series = pd.concat([time_series, result], ignore_index=True)

        self.set_time_diff(time_series, "time")

        return time_series

    def get_idle_consumption(self, timestamps):
        # Set power as the only model variable temporarily
        model_variables = self.model_variables
        self.model_variables = ["power"]

        # Get power only from idle periods
        filtered_timestamps = [t for t in timestamps if t[3] == "IDLE"]
        time_series = self.get_time_series(filtered_timestamps, include_idle=True)

        # Set the model variables to their original value
        self.model_variables = model_variables

        # Return idle consumption as mean power in idle periods
        return time_series["power"].mean()

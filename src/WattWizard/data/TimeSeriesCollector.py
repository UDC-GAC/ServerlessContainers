import warnings
import pandas as pd
from datetime import datetime, timedelta

from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.logs.logger import log
from src.WattWizard.influxdb.influxdb_queries import var_query
from src.WattWizard.influxdb.influxdb import query_influxdb

OUT_RANGE = 1.5
warnings.simplefilter(action='ignore', category=FutureWarning)


class TimeSeriesCollector:

    influxdb_bucket = None
    model_variables = None

    def __init__(self, model_variables, influxdb_bucket):
        self.model_variables = model_variables
        self.influxdb_bucket = influxdb_bucket

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
    def get_timestamp_from_line(start_line, stop_line, offset):
        start_str = " ".join(start_line.split(" ")[-2:]).strip()
        stop_str = " ".join(stop_line.split(" ")[-2:]).strip()
        exp_type = start_line.split(" ")[1]
        if exp_type == "IDLE":
            offset = 0
        start = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S%z') + timedelta(seconds=offset)
        stop = datetime.strptime(stop_str, '%Y-%m-%d %H:%M:%S%z') - timedelta(seconds=offset)
        return [(start, stop, exp_type)]

    def __set_model_variables(self, v):
        if v is not None:
            self.model_variables = v
        raise Exception("Trying to set model variables from TimeSeriesCollector as None")

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
            ts_line = self.get_timestamp_from_line(start_line, stop_line, 20)
            timestamps.append(ts_line[0])
        log(f"Timestamps belong to period [{timestamps[0][0]}, {timestamps[-1][1]}]")
        return timestamps

    # Get data for a given period (obtained from timestamps)
    def get_experiment_data(self, timestamp):
        start_date, stop_date, exp_type = timestamp
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_str = stop_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Get model variables time series and merge data
        exp_data = pd.DataFrame()
        for var in self.model_variables:
            df = query_influxdb(var_query[var], start_str, stop_str, self.influxdb_bucket)
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
        except KeyError:
            log(f"Error getting data between {start_date} and {stop_date}", "ERR")
            print(exp_data)
            exit(1)
        return exp_data

    # Get model variables time series from timestamps
    def get_time_series(self, timestamps, include_idle=False):
        time_series = pd.DataFrame(columns=self.model_variables)

        # Remove idle periods when include_idle is False
        filtered_timestamps = [t for t in timestamps if include_idle or t[2] != "IDLE"]

        for timestamp in filtered_timestamps:
            result = self.get_experiment_data(timestamp)
            result.dropna(inplace=True)
            time_series = pd.concat([time_series, result], ignore_index=True)

        return time_series

    def get_idle_consumption(self, timestamps):
        # Set power as the only model variable temporarily
        model_variables = self.model_variables
        self.model_variables = ["power"]

        # Get power only from idle periods
        filtered_timestamps = [t for t in timestamps if t[2] == "IDLE"]
        time_series = self.get_time_series(filtered_timestamps, include_idle=True)

        # Set the model variables to their original value
        self.model_variables = model_variables

        # Return idle consumption as mean power in idle periods
        return time_series["power"].mean()


import os
import pandas as pd
from src.WattWizard.logs.logger import log
from src.WattWizard.data.TimeSeriesParallelCollector import TimeSeriesParallelCollector


class DataLoader:

    def __init__(self, config):
        self.config = config
        self.ts_collector = TimeSeriesParallelCollector(
            self.config.get_argument("model_variables"),
            self.config.get_argument("influxdb_host"),
            self.config.get_argument("influxdb_bucket"),
            self.config.get_argument("influxdb_token"),
            self.config.get_argument("influxdb_org"))

    @staticmethod
    def _read_from_csv(path):
        log(f"Reading CSV file: {path}")
        return pd.read_csv(path)

    @staticmethod
    def _save_to_csv(path, df):
        log(f"Saving time series to CSV for future reuse: {path}")
        df.to_csv(path)

    @staticmethod
    def _build_path(base_dir, filename, ext, idle=False, join=False):
        suffix = ('_IDLE' if idle else '') + ('_JOIN' if join and not idle else '') if ext == 'csv' else ''
        return os.path.join(base_dir, f"{filename}{suffix}.{ext}")

    def load_time_series(self, structure, base_dir, filename, idle=False, join=False):
        # Create separate directory for CSV files
        os.makedirs(f"{base_dir}/.csv_cache", exist_ok=True)
        # First, try getting data from CSV file if already exists
        csv_path = self._build_path(f"{base_dir}/.csv_cache", filename, "csv", idle, join)
        if os.path.exists(csv_path):
            try:
                df = self._read_from_csv(csv_path)
                # Check all the model variables are present in train time series (not idle)
                if idle or all(v in df for v in self.config.get_argument("model_variables")):
                    return df
                log(f"Some model variables are missing in CSV file. Getting data from InfluxDB and updating CSV file")
            except Exception as e:
                log(f"Error while reading {csv_path}: {str(e)}", "WARN")

        # If CSV not available, get data from InfluxDB
        timestamps_path = self._build_path(base_dir, filename, "timestamps")
        log(f"Retrieving data from InfluxDB using timestamps file: {timestamps_path}")
        # Parse file with the timestamps corresponding to InfluxDB data
        train_timestamps = self.ts_collector.parse_timestamps(timestamps_path)
        # Get time series from InfluxDB
        df = self.ts_collector.get_time_series(structure, train_timestamps,
                                               mode="only_idle" if idle else "no_idle", join=join)
        # Save time series to CSV for future reuse
        self._save_to_csv(csv_path, df)

        return df

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
        if not os.path.exists(path):
            log(f"Saving time series to CSV for future reuse: {path}")
            df.to_csv(path)

    @staticmethod
    def _build_path(base_dir, filename, ext, idle=False):
        return os.path.join(base_dir, f"{filename}{'_idle' if idle else ''}.{ext}")

    def load_time_series(self, structure, base_dir, filename, idle=False):
        # First, try getting data from CSV file
        csv_path = self._build_path(base_dir, filename, "csv", idle)
        if os.path.exists(csv_path):
            try:
                log(f"Reading CSV file: {csv_path}")
                df = pd.read_csv(csv_path)
                return df
            except Exception as e:
                log(f"Error while reading {csv_path}: {str(e)}", "WARN")

        # If CSV not available, get data from InfluxDB
        timestamps_path = self._build_path(base_dir, filename, "timestamps", idle)
        log(f"Retrieving data from InfluxDB using timestamps file: {timestamps_path}")
        # Parse file with the timestamps corresponding to InfluxDB data
        train_timestamps = self.ts_collector.parse_timestamps(timestamps_path)
        # Get time series from InfluxDB
        df = self.ts_collector.get_time_series(structure, train_timestamps, mode="only_idle" if idle else "no_idle")
        # Save time series to CSV for future reuse
        self._save_to_csv(csv_path, df)

        return df

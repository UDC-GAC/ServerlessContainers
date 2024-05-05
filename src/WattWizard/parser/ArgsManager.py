import os

from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.influxdb.InfluxDBCollector import InfluxDBHandler


SUPPORTED_ARGS = ['verbose', 'influxdb_host', 'influxdb_bucket', 'influxdb_token', 'influxdb_org',
                  'prediction_methods', 'model_variables', 'host_timestamps_dir', 'container_timestamps_dir',
                  'host_train_files', 'container_train_files', 'plot_time_series', 'plot_time_series_dir']
SUPPORTED_VARS = ["load", "user_load", "system_load", "wait_load", "freq", "sumfreq", "temp"]
SUPPORTED_PRED_METHODS = ["mlpregressor", "sgdregressor", "polyreg"]

WATTWIZARD_DIR = MyConfig.get_project_dir()


class ArgsManager:

    def __init__(self, cli_args=None, config_file_args=None):
        self.cli_args = cli_args
        self.config_file_args = config_file_args

    @staticmethod
    def check_files_exist(files):
        for file in files:
            if not os.path.isfile(file):
                log(f"File {file} is not a file", "ERR")
                exit(1)
            if not os.access(file, os.R_OK):
                log(f"File {file} is not accesible: check file permissions", "ERR")
                exit(1)

    @staticmethod
    def check_dirs_exist(dirs):
        for dir in dirs:
            if not os.path.exists(dir):
                log(f"Directory {dir} doesn't exist", "ERR")
                exit(1)
            if not os.path.isdir(dir):
                log(f"Directory {dir} is not a directory", "ERR")
                exit(1)
            if not os.access(dir, os.R_OK):
                log(f"Directory {dir} is not accesible: check directory permissions", "ERR")
                exit(1)

    @staticmethod
    def check_supported_values(arg_name, current_values, supported_values):
        for value in current_values:
            if value not in supported_values:
                log(f"Value '{value}' for argument '{arg_name}' not supported", "ERR")
                log(f"Supported values: {supported_values}", "ERR")
                exit(1)

    def validate_args(self):
        my_config = MyConfig.get_instance()
        args = my_config.get_arguments()

        structure_without_train_files = 0
        influxdb_args = 0
        for arg_name in args:

            if arg_name == "verbose":
                pass  # Nothing to do for verbose

            elif arg_name == "output":
                pass  # Nothing to do for output

            elif arg_name.startswith("influxdb"):
                influxdb_args += 1  # Count InfluxDB arguments

            elif arg_name == "prediction_methods":
                self.check_supported_values(arg_name, args[arg_name], SUPPORTED_PRED_METHODS)

            elif arg_name == "host_timestamps_dir":
                pass  # Nothing to do for host_timestamps_dir (already checked in host_train_files)

            elif arg_name == "container_timestamps_dir":
                pass  # Nothing to do for container_timestamps_dir (already checked in container_train_files)

            elif arg_name == "host_train_files":
                if len(args[arg_name]) == 0:
                    structure_without_train_files += 1
                self.check_files_exist(list(set(args[arg_name]) - {"NPT"}))

            elif arg_name == "container_train_files":
                if len(args[arg_name]) == 0:
                    structure_without_train_files += 1
                self.check_files_exist(list(set(args[arg_name]) - {"NPT"}))

            elif arg_name == "model_variables":
                self.check_supported_values(arg_name, args[arg_name], SUPPORTED_VARS)

            elif arg_name == "plot_time_series":
                pass

            elif arg_name == "plot_time_series_dir":
                pass

            else:
                log(f"Argument {arg_name} is not supported", "ERR")
                exit(1)

        if structure_without_train_files == 2:
            log(f"No host or container train files have been specified. At least one file (or NPT) "
                f"must be indicated for one of these structures. Otherwise, no model would be created.", "ERR")
            exit(1)

        if influxdb_args == 4:
            with InfluxDBHandler(args["influxdb_host"], args["influxdb_bucket"], args["influxdb_token"], args["influxdb_org"]) as conn:
                conn.check_influxdb_connection()
                conn.check_bucket_exists()
        else:
            log(f"Missing some InfluxDB parameter. InfluxDB host, bucket, token and organization must be specified", "ERR")
            exit(1)

    def manage_args(self):
        my_config = MyConfig.get_instance()

        # If CLI arg is provided set as config, otherwise, use config file values
        for arg_name in SUPPORTED_ARGS:
            if self.cli_args[arg_name] is not None:
                my_config.add_argument(arg_name, self.cli_args[arg_name])
            else:
                my_config.add_argument(arg_name, self.config_file_args[arg_name])

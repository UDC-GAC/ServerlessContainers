import os

from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.influxdb.InfluxDBCollector import InfluxDBHandler


SUPPORTED_ARGS = [
    'verbose',
    'server_mode',
    'influxdb_host',
    'influxdb_bucket',
    'influxdb_token',
    'influxdb_org',
    'structures',
    'prediction_methods',
    'model_variables',
    'sockets',
    'cores_distribution',
    'csv_caching_train',
    'csv_caching_test',
    'join_train_timestamps',
    'train_timestamps_dir',
    'train_files',
    'join_test_timestamps',
    'test_timestamps_dir',
    'test_files',
    'plot_time_series',
    'plot_time_series_dir'
]

SUPPORTED_STRUCTURES = ["container", "host", "core"]
SUPPORTED_PRED_METHODS = ["mlpregressor", "sgdregressor", "polyreg", "interpolation", "multisocket", "randomforest", "arxmodel"]
SUPPORTED_VARS = ["load", "user_load", "system_load", "avgfreq", "sumfreq", "p_user_load", "p_system_load", "l_user_load", "l_system_load", "wait_load", "temp"]

WATTWIZARD_DIR = MyConfig.get_project_dir()


class ArgsManager:

    def __init__(self, cli_args=None, config_file_args=None):
        self.cli_args = cli_args
        self.config_file_args = config_file_args
        # Add here all the arguments that must be validated
        self.arg_validators = {
            "structures":             lambda v: self.check_supported_values("structures", v, SUPPORTED_STRUCTURES),
            "prediction_methods":     lambda v: self.check_supported_values("prediction_methods", v, SUPPORTED_PRED_METHODS),
            "model_variables":        lambda v: self.check_supported_values("model_variables", v, SUPPORTED_VARS),
            "sockets":                lambda v: self.check_supported_values("sockets", [v], [2]),
            "train_files":            lambda v: self.check_train_files(v),
            "test_files":             lambda v: self.check_test_files(v),
        }

    @staticmethod
    def check_files_exist(files):
        for file in files:
            if not os.path.isfile(file):
                log(f"File {file} is not a file", "ERR")
                exit(1)
            if not os.access(file, os.R_OK):
                log(f"File {file} is not accesible: check file permissions", "ERR")
                exit(1)

    def check_train_files(self, arg_value):
        if len(arg_value) == 0:
            log(f"No train files have been specified. At least one file (or NPT) must be indicated. "
                f"Otherwise, no model would be created.", "ERR")
            exit(1)
        # Remove duplicates and None values through set subtraction
        self.check_files_exist(list(set(arg_value) - {None}))

    def check_test_files(self, arg_value):
        if len(arg_value) > 0:
            self.check_files_exist(arg_value)

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

    @staticmethod
    def check_influxdb_args(args):
        # If InfluxDB host is not specified, check if CSV caching is activated
        if not args.get("influxdb_host", ""):
            if not args.get("csv_caching_train", False):
                log("InfluxDB host not specified and train CSV caching is not activated", "ERR")
                exit(1)
            if args.get("test_files", "") and not args.get("csv_caching_test", False):
                log(f"InfluxDB host not specified and test CSV caching is not activated while test files are provided", "ERR")
                exit(1)
            log(f"InfluxDB host not specified, data will be retrieved from CSV cache", "WARN")
            return

        # If InfluxDB host is specified, check that all InfluxDB parameters are provided
        influxdb_args = sum(1 for name in args if name.startswith("influxdb"))
        if influxdb_args == 4:
            with InfluxDBHandler(args["influxdb_host"], args["influxdb_bucket"], args["influxdb_token"], args["influxdb_org"]) as conn:
                conn.check_influxdb_connection()
                conn.check_bucket_exists()
        else:
            log(f"Missing some InfluxDB parameter. InfluxDB host, bucket, token and organization must be specified", "ERR")
            exit(1)

    @staticmethod
    def check_cores_distribution(args):
        if not isinstance(args['cores_distribution'], dict):
            log(f"A dict was expected as cores distribution but '{type(args['cores_distribution'])}' was found", "ERR")
            exit(1)
        if len(args['cores_distribution'].keys()) < args['sockets']:
            log(f"{args['sockets']} sockets were expected in cores distribution but only '{len(args['cores_distribution'].keys())}' was found", "ERR")
            exit(1)

    def validate_args(self):
        my_config = MyConfig.get_instance()
        args = my_config.get_arguments()

        for name, value in args.items():
            # Check if the argument is supported
            if name not in SUPPORTED_ARGS:
                log(f"Argument {name} is not supported", "ERR")
                exit(1)

            # Check if the argument must be validated
            validate = self.arg_validators.get(name)
            if validate:
                validate(value)

        # Perform additional validations that require information from more than one argument
        self.check_influxdb_args(args)
        self.check_cores_distribution(args)

    def manage_args(self):
        my_config = MyConfig.get_instance()

        # If CLI arg is provided set as config, otherwise, use config file values
        for arg_name in SUPPORTED_ARGS:
            if self.cli_args[arg_name] is not None:
                my_config.add_argument(arg_name, self.cli_args[arg_name])
            else:
                my_config.add_argument(arg_name, self.config_file_args[arg_name])

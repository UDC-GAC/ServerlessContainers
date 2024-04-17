import os

from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.influxdb.influxdb import check_bucket_exists


SUPPORTED_ARGS = ['verbose', 'influxdb_bucket', 'prediction_methods', 'timestamps_dir', 'train_files', 'model_variables']
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
    def check_supported_values(arg_name, current_values, supported_values):
        for value in current_values:
            if value not in supported_values:
                log(f"Value '{value}' for argument '{arg_name}' not supported", "ERR")
                log(f"Supported values: {supported_values}", "ERR")
                exit(1)

    def validate_args(self):
        my_config = MyConfig.get_instance()
        args = my_config.get_arguments()

        for arg_name in args:
            match arg_name:
                case "verbose":
                    pass  # Nothing to do for verbose
                case "output":
                    pass  # Nothing to do for output
                case "influxdb_bucket":
                    check_bucket_exists(args[arg_name])
                case "prediction_methods":
                    self.check_supported_values(arg_name, args[arg_name], SUPPORTED_PRED_METHODS)

                case "timestamps_dir":
                    pass  # Nothing to do for timestamps_dir (already checked in train_files)

                case "train_files":
                    self.check_files_exist(list(set(args[arg_name]) - {"NPT"}))

                case "model_variables":
                    self.check_supported_values(arg_name, args[arg_name], SUPPORTED_VARS)

                case _:
                    log(f"Argument {arg_name} is not supported", "ERR")
                    exit(1)

    def manage_args(self):
        my_config = MyConfig.get_instance()

        # If CLI arg is provided set as config, otherwise, use config file values
        for arg_name in SUPPORTED_ARGS:
            if self.cli_args[arg_name] is not None:
                my_config.add_argument(arg_name, self.cli_args[arg_name])
            else:
                my_config.add_argument(arg_name, self.config_file_args[arg_name])

    # def map_train_files_to_models(train_files):
    #     for p, file in zip(config.prediction_methods, train_files):
    #         if file != "":
    #             if p in config.train_files_models_map:
    #                 config.train_files_models_map[p].append(file)
    #             else:
    #                 config.train_files_models_map[p] = [file]
    #         elif p not in config.train_files_models_map:
    #             config.train_files_models_map[p] = ["NPT"]
    #         else:
    #             config.train_files_models_map[p].append("NPT")
    #
    # def map_one_file_to_all_models(train_file):
    #     for p in config.prediction_methods:
    #         if p in config.train_files_models_map:
    #             config.train_files_models_map[p].append(train_file)
    #         else:
    #             config.train_files_models_map[p] = [train_file]
    #
    # def check_not_duplicated_models():
    #     log(f"Prediction methods: {config.prediction_methods}")
    #     for p in config.prediction_methods:
    #         unique_files_list = []
    #         if p in config.train_files_models_map:
    #             for file in config.train_files_models_map[p]:
    #                 if file not in unique_files_list:
    #                     unique_files_list.append(file)
    #                     count_file = config.train_files_models_map[p].count(file)
    #                     if count_file > 1:
    #                         log(f"Model with prediction method {p} and train file {file} appears {count_file} times.", "WARN")
    #                         log(f"Skipping duplicated models...", "WARN")
    #             config.train_files_models_map[p] = unique_files_list
    #         log(f"Train_files for method {p}: {config.train_files_models_map[p]}")



    # def set_args(args):
    #     config.verbose = args.verbose
    #     config.model_vars = args.vars.split(',')
    #     config.influxdb_bucket = args.bucket
    #     config.prediction_methods = args.prediction_methods.split(',')
    #     if args.train_timestamps_list:
    #         map_train_files_to_models(args.train_timestamps_list.split(','))
    #     elif args.train_timestamps:
    #         map_one_file_to_all_models(args.train_timestamps)
    #     else:
    #         map_one_file_to_all_models("NPT") # NPT = Not PreTrained
    #
    #     # Remove duplicates from prediction methods
    #     # From now on this list is used as a list of unique elements
    #     config.prediction_methods = list(set(config.prediction_methods))
    #
    #     # Check there aren't two or more models with same prediction method and train file
    #     check_not_duplicated_models()




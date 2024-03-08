import os
import argparse
from argparse import RawTextHelpFormatter

from src.WattWizard.logs.logger import log
from src.WattWizard.config import config
from src.WattWizard.influxdb.influxdb import check_bucket_exists


def create_parser():
    parser = argparse.ArgumentParser(
        description="CPU Power Modeling from Time Series.",
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        "-b",
        "--bucket",
        help="If pretrain data is specified you must indicate an InfluxDB Bucket to retrieve data from.",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="out",
        help="Directory to save time series plots and results. By default is './out'.",
    )

    parser.add_argument(
        "-p",
        "--prediction-methods",
        default="sgdregressor",
        help="Comma-separated list of methods used to predict CPU power consumption. By default is a SGD Regressor. Supported methods:\n\
\tmlpregressor\t\t\tMultilayer Perceptron Regressor\n\
\tsgdregressor\t\t\tPolynomial Regression fitted by SGD\n\
\tpolyreg\t\t\t\tPolynomial Regression (Doesn't have support for online learning)",
    )

    parser.add_argument(
        "--train-timestamps",
        default="",
        help="If train timestamps file is provided, all models will be pretrained with this file. This file must store time series \n\
timestamps from pretrain data in proper format. Check README.md to see timestamps proper format.",
    )

    parser.add_argument(
        "--train-timestamps-list",
        default="",
        help="If various prediction methods are used you can specify different train timestamp files for each method.\n\
They must be specified in same order as prediction methods. If a filename is not specified between two commas, \n\
the method corresponding to that position will not be pre-trained.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase output verbosity",
    )

    parser.add_argument(
        "--vars",
        default="user_load,system_load",
        help="Comma-separated list of variables to use in the model. Commonly known as features. \
\nSupported values: user_load, system_load, wait_load, freq, sumfreq.",
    )

#     parser.add_argument(
#         "--model-files-list",
#         default="",
#         help="Comma-separated list of .joblib files containing pretrained models. Instead of creating a model from scratch and\n\
# pretrained it (or not). You can create and train your own models separately and save their corresponding .joblib files to\n\
# use it with wattwizard.",
#     )

    return parser


def check_valid_vars(model_vars):
    aux = set(model_vars) - set(config.SUPPORTED_VARS)
    if aux:
        log(f"{aux} not supported. Supported vars: {config.SUPPORTED_VARS}", "ERR")
        exit(1)


def check_prediction_methods(pred_methods):
    for p in pred_methods:
        if p not in config.SUPPORTED_PRED_METHODS:
            log(f"Prediction method ({p}) not supported", "ERR")
            log(f"Supported methods: {config.SUPPORTED_PRED_METHODS}", "ERR")
            exit(1)


def check_files_exists(file_list):
    for file in file_list:
        if not os.path.exists(file) and file != "":
            log(f"Specified non existent file: {file}", "ERR")
            exit(1)

def map_train_files_to_models(train_files):
    for p, file in zip(config.prediction_methods, train_files):
        if file != "":
            if p in config.train_files_models_map:
                config.train_files_models_map[p].append(file)
            else:
                config.train_files_models_map[p] = [file]
        elif p not in config.train_files_models_map:
            config.train_files_models_map[p] = ["NPT"]
        else:
            config.train_files_models_map[p].append("NPT")

def map_one_file_to_all_models(train_file):
    for p in config.prediction_methods:
        if p in config.train_files_models_map:
            config.train_files_models_map[p].append(train_file)
        else:
            config.train_files_models_map[p] = [train_file]

def check_not_duplicated_models():
    log(f"Prediction methods: {config.prediction_methods}")
    for p in config.prediction_methods:
        unique_files_list = []
        if p in config.train_files_models_map:
            for file in config.train_files_models_map[p]:
                if file not in unique_files_list:
                    unique_files_list.append(file)
                    count_file = config.train_files_models_map[p].count(file)
                    if count_file > 1:
                        log(f"Model with prediction method {p} and train file {file} appears {count_file} times.", "WARN")
                        log(f"Skipping duplicated models...", "WARN")
            config.train_files_models_map[p] = unique_files_list
        log(f"Train_files for method {p}: {config.train_files_models_map[p]}")

def check_args(args):
    check_valid_vars(args.vars.split(','))
    check_prediction_methods(args.prediction_methods.split(','))
    if args.train_timestamps:
        check_files_exists([args.train_timestamps])
        check_bucket_exists(args.bucket)
    if args.train_timestamps_list:
        check_files_exists(args.train_timestamps_list.split(','))
        check_bucket_exists(args.bucket)

def set_args(args):
    config.verbose = args.verbose
    config.model_vars = args.vars.split(',')
    config.influxdb_bucket = args.bucket
    config.prediction_methods = args.prediction_methods.split(',')
    if args.train_timestamps_list:
        map_train_files_to_models(args.train_timestamps_list.split(','))
    elif args.train_timestamps:
        map_one_file_to_all_models(args.train_timestamps)
    else:
        map_one_file_to_all_models("NPT") # NPT = Not PreTrained

    # Remove duplicates from prediction methods
    # From now on this list is used as a list of unique elements
    config.prediction_methods = list(set(config.prediction_methods))

    # Check there aren't two or more models with same prediction method and train file
    check_not_duplicated_models()

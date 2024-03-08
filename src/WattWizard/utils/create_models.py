import re

from src.WattWizard.data.process import parse_timestamps, get_time_series, get_idle_consumption
from src.WattWizard.app.model_operations import time_series_to_train_data
from src.WattWizard.logs.logger import log
from src.WattWizard.config import config
from src.WattWizard.model import *

time_series = {}
idle_consumption = {}
processed_files = {}


def get_file_name(file):
    pattern = r'\/([^/]+)\.'
    occurrences = re.findall(pattern, file)
    return occurrences[-1]


def pretrain_model(model_instance, train_file, pred_method):
    # Check if same train timestamps file was already used
    prev_method = None
    for method, file in processed_files.items():
        if file == train_file:
            prev_method = method
            break

    # If same file was already used it isn't necessary to get time series again
    if prev_method is None:
        log(f"Parsing train timestamps from {train_file}")
        train_timestamps = parse_timestamps(train_file)

        log("Getting model variables time series from corresponding period")
        time_series[pred_method] = get_time_series(model_instance.get_model_vars() + ["power"], train_timestamps)

        log("Idle consumption will be inferred from pretrain data")
        idle_consumption[pred_method] = get_idle_consumption(train_timestamps)
    else:
        log(f"Method {pred_method} use same timestamps file ({train_file}) as method {prev_method}")
        log(f"Reusing time series obtained for method {prev_method}")
        time_series[pred_method] = time_series[prev_method]
        idle_consumption[pred_method] = idle_consumption[prev_method]
    processed_files[pred_method] = train_file

    # Pretrain model with collected time series
    try:
        X_train, y_train = time_series_to_train_data(model_instance, time_series[pred_method])
        model_instance.pretrain(X_train, y_train)
        model_instance.set_idle_consumption(idle_consumption[pred_method])
        log("Model successfully pretrained") # TODO: Add more relevant info
    except TypeError as e:
        log(f"{str(e)}", "ERROR")


def create_model_instance(pred_method, train_file=None):
    # Set model name based on train file name
    if train_file:
        train_file_name = get_file_name(train_file)
        model_name = f"{pred_method}_{train_file_name}"
    else:
        model_name = f"{pred_method}_NPT" # NPT = Not PreTrained

    instance = None
    if model_name not in config.model_instances:
        if pred_method == "mlpregressor":
            instance = Perceptron()
        elif pred_method == "sgdregressor":
            instance = SGDRegression()
        elif pred_method == "polyreg":
            instance = PolynomialRegression()
        else:
            log(f"Trying to create model with unsupported prediction method ({pred_method})", "ERR")
            exit(1)
        config.model_instances[model_name] = instance
        log(f"Model with name {model_name} has been successfully initialized")
        return config.model_instances[model_name]
    else:
        log(f"Model with name {model_name} already exists. Skipping model...", "WARN")
        log(f"This means you have already specified a model with same characteristics", "WARN")
        log(f"Prediction method = {pred_method} Train file = {train_file}", "WARN")
        return None


def run():
    for p in config.prediction_methods:
        for train_file in config.train_files_models_map[p]:
            if train_file == "NPT":  # NPT = Not PreTrained
                train_file = None
                if p in config.STATIC_METHODS:
                    log(f"Prediction method {p} doesn't support online learning, so it's mandatory to pretrain the model", "ERR")
                    exit(1)
            model_instance = create_model_instance(p, train_file)
            if model_instance:
                model_instance.set_model_vars(config.model_vars)
                if train_file:
                    pretrain_model(model_instance, train_file, p)

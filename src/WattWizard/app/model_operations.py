import numpy as np
import time
from src.WattWizard.config import config


def check_model_exists(model_name):
    if model_name is None:
        raise TypeError('A model name must be specified: /predict/<model_name>')
    if model_name not in config.model_instances:
        raise TypeError(f'Model with name {model_name} doesn\'t exists')


def check_valid_values(values_dict):
    for var in values_dict:
        if values_dict[var] < config.cpu_limits[var]["min"]:
            raise ValueError(f'Too low {var} value ({values_dict[var]}). '
                             f'Minimum value is {config.cpu_limits[var]["min"]}.')
        if values_dict[var] > config.cpu_limits[var]["max"]:
            raise ValueError(f'{var} value ({values_dict[var]}) exceeds its maximum. '
                             f'Maximum value is {config.cpu_limits[var]["max"]}.')


def get_pred_method(model_name):
    pattern = r'([^_]+)_'
    occurrences = re.findall(pattern, model_name)
    return occurrences[0]


def get_desired_power(req):
    value = req.args.get("desired_power", type=float)
    if value is None:
        raise TypeError(f"Missing desired power value in request. You must include it as follows"
                        f" <url>:<port>/predict?desired_power=<value>")
    return value


def time_series_to_train_data(model_instance, time_series):
    x_values = []
    for var in model_instance.model_vars:
        if var in time_series:
            x_values.append(time_series[var].values.reshape(-1, 1))
        else:
            raise TypeError(f"Missing variable {var} in train time series")
    x_stack = np.hstack(x_values)
    y = time_series["power"].values
    return x_stack, y


def json_to_train_data(model_instance, json_data):
    if "power" in json_data:
        y = np.array(json_data["power"])
    else:
        raise TypeError("Missing power data in JSON")
    x_values = []
    for var in model_instance.model_vars:
        if var not in json_data:
            raise TypeError(f"Missing {var} data in JSON")
        x_values.append(np.array(json_data[var]).reshape(-1, 1))
    x_stack = np.hstack(x_values)
    return x_stack, y


def request_to_dict(model_instance, request):
    x_values = {}
    for var in model_instance.model_vars:
        value = request.args.get(var, type=float)
        if value is not None:
            x_values[var] = value
        else:
            raise TypeError(f"Missing {var} value in request. You must include it as follows"
                            f" <url>:<port>/predict?{var}=<value>")
    return x_values


def get_inverse_prediction(model_instance, current_X, desired_power, dynamic_var):
    t0 = time.perf_counter()
    current_power = model_instance.predict(current_X)
    error = abs(desired_power - current_power)
    max_error = 0.001
    max_iters = 100
    count_iters = 0
    min_value = config.cpu_limits[dynamic_var]["min"]
    max_value = config.cpu_limits[dynamic_var]["max"]
    #print(f"Initial x values: {current_X}")
    #print(f"Initial power prediction: {current_power}")
    #print(f"Desired power prediction: {desired_power}")
    while error > max_error and count_iters < max_iters and min_value < current_X[dynamic_var] < max_value:
        current_X[dynamic_var] = desired_power * current_X[dynamic_var] / current_power
        current_power = model_instance.predict(current_X)
        error = abs(desired_power - current_power)
        count_iters += 1
        #print(f"[Iteration {count_iters}] Current {dynamic_var} value: {current_X[dynamic_var]}")
        #print(f"[Iteration {count_iters}] Power prediction: {current_power}")
        #print(f"[Iteration {count_iters}] Error: {error}")
    t1 = time.perf_counter()
    print(f"Execution time {t1 - t0}")
    if current_X[dynamic_var] > max_value:
        current_X[dynamic_var] = max_value
    return current_X[dynamic_var]

from src.WattWizard.data.TimeSeriesParallelCollector import TimeSeriesParallelCollector
from src.WattWizard.app.app_utils import time_series_to_train_data
from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler

time_series = {}
idle_consumption = {}
processed_models = []


def pretrain_model(ts_collector, structure, model_instance, train_file, pred_method):
    # Check if same train timestamps file was already used
    previous_method = None
    for model in processed_models:
        if model['train_file'] == train_file:
            previous_method = model['prediction_method']
            break

    # If same file was already used it isn't necessary to get time series again
    if previous_method is None:
        log(f"Processing timestamps file: {train_file}")
        train_timestamps = ts_collector.parse_timestamps(train_file)
        time_series[pred_method] = ts_collector.get_time_series(train_timestamps, structure == "container")
        idle_consumption[pred_method] = ts_collector.get_idle_consumption(train_timestamps)
    else:
        log(f"File {train_file} was previously processed for method {previous_method}")
        log(f"Reusing time series for method {pred_method}")
        time_series[pred_method] = time_series[previous_method]
        idle_consumption[pred_method] = idle_consumption[previous_method]
    processed_models.append({"train_file": train_file, "prediction_method": pred_method})

    # Pretrain model with collected time series
    try:
        X_train, y_train = time_series_to_train_data(model_instance, time_series[pred_method])
        model_instance.pretrain(X_train, y_train)
        model_instance.set_idle_consumption(idle_consumption[pred_method])
        train_file_name =ModelHandler.get_file_name(train_file)
        log(f"Model using prediction method {pred_method} successfully pretrained using {train_file_name} timestamps")
    except TypeError as e:
        log(f"{str(e)}", "ERROR")


def run():
    my_config = MyConfig.get_instance()
    model_variables = my_config.get_argument("model_variables")

    # Get InfluxDB info
    influxdb_host = my_config.get_argument("influxdb_host")
    influxdb_bucket = my_config.get_argument("influxdb_bucket")
    influxdb_token = my_config.get_argument("influxdb_token")
    influxdb_org = my_config.get_argument("influxdb_org")

    print(my_config.get_logo())
    for line in my_config.get_summary():
        log(line)

    model_handler = ModelHandler.get_instance()
    ts_collector = TimeSeriesParallelCollector(model_variables + ["power"], influxdb_host, influxdb_bucket, influxdb_token, influxdb_org)

    for structure in ["host", "container"]:
        ts_collector.set_structure(structure)
        for prediction_method in my_config.get_argument("prediction_methods"):
            for train_file in my_config.get_argument(f"{structure}_train_files"):
                train_file = None if train_file == "NPT" else train_file  # NPT = Not Pre-Trained
                if train_file is None and ModelHandler.is_static(prediction_method):
                    log(f"Prediction method {prediction_method} doesn't support online learning, "
                        f"so it's mandatory to pretrain the model. Model will be discarded", "WARN")
                    continue
                model_name = model_handler.add_model(structure, prediction_method, train_file)
                model = model_handler.get_model_by_name(structure, model_name)
                if model and model['instance']:
                    model['instance'].set_model_vars(model_variables)
                    if model['train_file']:
                        pretrain_model(ts_collector, structure, model['instance'], model['train_file'], model['prediction_method'])

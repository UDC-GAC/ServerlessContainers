from src.WattWizard.data.TimeSeriesParallelCollector import TimeSeriesParallelCollector
from src.WattWizard.data.TimeSeriesPlotter import TimeSeriesPlotter
from src.WattWizard.app.app_utils import time_series_to_train_data
from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler



class ModelBuilder:

    time_series = None
    idle_consumption = None
    processed_files = None
    config = None
    model_handler = None
    ts_plotter = None
    ts_collector = None

    def __init__(self):
        self.time_series = {}
        self.idle_consumption = {}
        self.processed_files = []
        self.config = MyConfig.get_instance()
        self.model_handler = ModelHandler.get_instance()
        self.ts_plotter = TimeSeriesPlotter()
        self.ts_collector = TimeSeriesParallelCollector(self.config.get_argument("model_variables") + ["power"],
                                                        self.config.get_argument("influxdb_host"),
                                                        self.config.get_argument("influxdb_bucket"),
                                                        self.config.get_argument("influxdb_token"),
                                                        self.config.get_argument("influxdb_org"))

    def add_processed_file(self, train_file, pred_method):
        self.processed_files.append({"path": train_file, "prediction_method": pred_method})

    def check_file_was_processed(self, train_file):
        for file in self.processed_files:
            if file["path"] == train_file:
                return file["pred_method"]
        return None

    def get_time_series_from_file(self, structure, train_file, pred_method):
        # Check if same train timestamps file was already used
        previous_method = self.check_file_was_processed(train_file)

        # If same file was already used it isn't necessary to get time series again
        if not previous_method:
            log(f"Processing timestamps file: {train_file}")
            train_timestamps = self.ts_collector.parse_timestamps(train_file)
            self.time_series[pred_method] = self.ts_collector.get_time_series(train_timestamps, structure == "container")
            self.idle_consumption[pred_method] = self.ts_collector.get_idle_consumption(train_timestamps)
        else:
            log(f"File {train_file} was previously processed for method {previous_method}")
            log(f"Reusing time series for method {pred_method}")
            self.time_series[pred_method] = self.time_series[previous_method]
            self.idle_consumption[pred_method] = self.idle_consumption[previous_method]

        self.add_processed_file(train_file, pred_method)

    def pretrain_model(self, structure, model):
        train_file_short_name = ModelHandler.get_file_name(model['train_file'])

        self.get_time_series_from_file(structure, model['train_file'], model['prediction_method'])
        # Pretrain model with collected time series
        try:
            X_train, y_train = time_series_to_train_data(model['instance'], self.time_series[model['prediction_method']])
            model['instance'].pretrain(X_train, y_train)
            model['instance'].set_idle_consumption(self.idle_consumption[model['prediction_method']])
            
            log(f"Model using prediction method {model['prediction_method']} successfully pretrained using {train_file_short_name} timestamps")
        except TypeError as e:
            log(f"{str(e)}", "ERROR")

        # Plot train time series if specified
        if self.config.get_argument("plot_time_series"):
            output_dir = f"{self.config.get_argument('plot_time_series_dir')}/{train_file_short_name}"
            self.ts_plotter.set_output_dir(output_dir)
            # TODO: Plot time series from train_file

    def initialize_model(self, structure, model_name):
        model = self.model_handler.get_model_by_name(structure, model_name)
        model_variables = self.config.get_argument("model_variables")

        if model and model['instance']:
            model['instance'].set_model_vars(model_variables)
            if model['train_file']:
                self.pretrain_model(structure, model)

    def build_models(self):
        print(self.config.get_logo())
        for line in self.config.get_summary():
            log(line)

        for structure in ["host", "container"]:
            self.ts_collector.set_structure(structure)
            for prediction_method in self.config.get_argument("prediction_methods"):
                for train_file in self.config.get_argument(f"{structure}_train_files"):
                    train_file = None if train_file == "NPT" else train_file  # NPT = Not Pre-Trained
                    if train_file is None and ModelHandler.is_static(prediction_method):
                        log(f"Prediction method {prediction_method} doesn't support online learning, "
                            f"so it's mandatory to pretrain the model. Model {prediction_method}_NPT will be discarded", "WARN")
                        continue
                    model_name = self.model_handler.add_model(structure, prediction_method, train_file)
                    self.initialize_model(structure, model_name)




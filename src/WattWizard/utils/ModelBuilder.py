from src.WattWizard.data.TimeSeriesParallelCollector import TimeSeriesParallelCollector
from src.WattWizard.data.TimeSeriesPlotter import TimeSeriesPlotter
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
        self.idle_time_series = {}
        self.processed_files = []
        self.config = MyConfig.get_instance()
        self.model_handler = ModelHandler.get_instance()
        self.ts_plotter = TimeSeriesPlotter()
        self.ts_collector = TimeSeriesParallelCollector(self.config.get_argument("model_variables") + ["power_pkg0", "power_pkg1"],
                                                        self.config.get_argument("influxdb_host"),
                                                        self.config.get_argument("influxdb_bucket"),
                                                        self.config.get_argument("influxdb_token"),
                                                        self.config.get_argument("influxdb_org"))

    def clear_processed_files(self):
        self.processed_files.clear()

    def add_processed_file(self, train_file, pred_method):
        self.processed_files.append({"path": train_file, "prediction_method": pred_method})

    def check_file_was_processed(self, train_file):
        for file in self.processed_files:
            if file["path"] == train_file:
                return file["prediction_method"]
        return None

    def get_time_series_from_file(self, structure, train_file, pred_method):
        # Check if same train timestamps file was already used
        previous_method = self.check_file_was_processed(train_file)

        # If same file was already used it isn't necessary to get time series again
        if not previous_method:
            log(f"Processing timestamps file: {train_file}")
            train_timestamps = self.ts_collector.parse_timestamps(train_file)
            self.time_series[pred_method] = self.ts_collector.get_time_series(train_timestamps, structure == "container")
            self.idle_time_series[pred_method] = self.ts_collector.get_idle_consumption(train_timestamps)
        else:
            log(f"File {train_file} was previously processed for method {previous_method}")
            log(f"Reusing time series for method {pred_method}")
            self.time_series[pred_method] = self.time_series[previous_method]
            self.idle_time_series[pred_method] = self.idle_time_series[previous_method]

        self.add_processed_file(train_file, pred_method)

    def pretrain_model(self, structure, model):

        self.get_time_series_from_file(structure, model['train_file_path'], model['prediction_method'])
        # Pretrain model with collected time series
        try:
            model['instance'].set_idle_consumption(self.idle_time_series[model['prediction_method']])
            model['instance'].pretrain(time_series=self.time_series[model['prediction_method']], data_type="df")

            log(f"Model using prediction method {model['prediction_method']} successfully pretrained using {model['train_file_name']} timestamps")

            # Plot train time series if specified
            if self.config.get_argument("plot_time_series"):
                output_dir = f"{self.config.get_argument('plot_time_series_dir')}/{structure}/{model['name']}/train"
                self.ts_plotter.set_output_dir(output_dir)
                log(f"Plotting train time series for model {model['name']}. Plot will be stored at {output_dir}")
                self.ts_plotter.plot_time_series(f"{model['name']} time series",
                                                 self.time_series[model['prediction_method']],
                                                 self.config.get_argument("model_variables"))
                self.ts_plotter.plot_vars_vs_power(self.time_series[model['prediction_method']], self.config.get_argument("model_variables"))

        except Exception as e:
            log(f"{str(e)}", "ERR")

    def initialize_model(self, structure, model):
        model_variables = self.config.get_argument("model_variables")

        if model and model['instance']:
            model['instance'].set_model_vars(model_variables)
            if model['train_file_path']:
                self.pretrain_model(structure, model)

    def test_models(self):
        for test_file in self.config.get_argument("test_files"):
            # Get test time series
            log(f"Processing timestamps file for tests: {test_file}")
            test_timestamps = self.ts_collector.parse_timestamps(test_file)
            test_time_series = self.ts_collector.get_time_series(test_timestamps, include_idle=False)

            # Test all models with the collected time series
            test_name = ModelHandler.get_file_name(test_file)
            for structure in self.config.get_argument("structures"):
                for model_name in self.model_handler.get_models_by_structure(structure):
                    model = self.model_handler.get_model_by_name(structure, model_name)
                    power_predicted = model['instance'].test(time_series=test_time_series, data_type="df")
                    test_time_series['power_predicted'] = power_predicted.flatten()

                    # Plot results
                    if self.config.get_argument("plot_time_series"):
                        output_dir = f"{self.config.get_argument('plot_time_series_dir')}/{structure}/{model['name']}/test"
                        self.ts_plotter.set_output_dir(output_dir)
                        log(f"Plotting test time series for model {model['name']} and test '{test_name}'.")
                        self.ts_plotter.plot_test_time_series(f"{model['name']}_{test_name}",
                                                              f"{model['name']} test time series ({test_name})",
                                                              test_time_series,
                                                              self.config.get_argument("model_variables"))

    def build_models(self):
        print(self.config.get_logo())
        for line in self.config.get_summary():
            log(line)

        for structure in self.config.get_argument("structures"):
            self.ts_collector.set_structure(structure)
            self.clear_processed_files()
            for prediction_method in self.config.get_argument("prediction_methods"):
                for train_file in self.config.get_argument(f"train_files"):
                    train_file = None if train_file == "NPT" else train_file  # NPT = Not Pre-Trained
                    if train_file is None and ModelHandler.is_static(prediction_method):
                        log(f"Prediction method {prediction_method} doesn't support online learning, so it's mandatory "
                            f"to pretrain the model. Model {prediction_method}_NPT will be discarded", "WARN")
                        continue
                    model = self.model_handler.add_model(structure, prediction_method, train_file)
                    self.initialize_model(structure, model)

        if len(self.config.get_argument("test_files")) > 0:
            self.test_models()
        else:
            log(f"The models won't be tested as no test files have been specified.")

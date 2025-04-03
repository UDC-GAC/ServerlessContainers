import os
import shutil
import pandas as pd

from src.WattWizard.data.TimeSeriesParallelCollector import TimeSeriesParallelCollector
from src.WattWizard.data.TimeSeriesPlotter import TimeSeriesPlotter
from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler

from sklearn.metrics import mean_squared_error, r2_score, max_error, mean_absolute_error, mean_absolute_percentage_error


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

    @staticmethod
    def is_hw_aware_compatible(file):
        try:
            with open(file, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            log(f"Error while parsing timestamps (file doesn't exists): {file}", "ERR")

        for i in range(0, len(lines)):
            exp_name = lines[i].split(" ")[0]
            exp_type = lines[i].split(" ")[1]
            if exp_name.startswith("CPU"):
                return True
            elif exp_type != "IDLE":
                return False
        return False

    def clear_processed_files(self):
        self.processed_files.clear()

    def add_processed_file(self, train_file, model_name):
        self.processed_files.append({"path": train_file, "model_name": model_name})

    def check_file_was_processed(self, train_file):
        for file in self.processed_files:
            if file["path"] == train_file:
                return file["model_name"]
        return None

    def save_time_series_to_csv(self, train_file_name, train_dataset):
        dest = os.path.join(self.config.get_argument("train_timestamps_dir"), train_file_name + ".csv")
        if not os.path.exists(dest):
            log(f"Saving train dataset to CSV file: {dest}")
            train_dataset.to_csv(dest)

    def get_time_series_from_csv(self, model_name, train_file, train_file_name):
        csv_file = os.path.join(self.config.get_argument("train_timestamps_dir"), train_file_name + ".csv")
        idle_csv_file = os.path.join(self.config.get_argument("train_timestamps_dir"), train_file_name + "_idle" + ".csv")
        if os.path.exists(csv_file) and os.path.exists(idle_csv_file):
            try:
                self.time_series[model_name] = pd.read_csv(csv_file)
                self.idle_time_series[model_name] = pd.read_csv(idle_csv_file)
                self.add_processed_file(train_file, model_name)
                return True
            except Exception as e:
                log(f"Some exception ocurred reading time series from CSV file {csv_file}: {str(e)}", "WARN")
                return False
        else:
            log(f"Can't get time series from CSV files {csv_file} and {idle_csv_file}. Some of the files doesn't exist, "
                f"getting data from InfluxDB through timestamps file")
            return False

    def get_time_series_from_file(self, structure, model_name, train_file, train_file_name):
        # Check if same train timestamps file was already used
        previous_model = self.check_file_was_processed(train_file)

        # If same file was already used it isn't necessary to get time series again
        if not previous_model:
            log(f"Processing timestamps file: {train_file}")
            train_timestamps = self.ts_collector.parse_timestamps(train_file)
            self.time_series[model_name] = self.ts_collector.get_time_series(train_timestamps, structure == "container")
            self.idle_time_series[model_name] = self.ts_collector.get_idle_consumption(train_timestamps)
            log("Saving time series to CSV")
            self.save_time_series_to_csv(train_file_name, self.time_series[model_name])
            self.save_time_series_to_csv(train_file_name + "_idle", self.idle_time_series[model_name])
        else:
            log(f"File {train_file} was previously processed for model {previous_model}")
            log(f"Reusing time series for model {model_name}")
            self.time_series[model_name] = self.time_series[previous_model]
            self.idle_time_series[model_name] = self.idle_time_series[previous_model]

        self.add_processed_file(train_file, model_name)

    def pretrain_model(self, structure, model):

        if not self.get_time_series_from_csv(model['name'], model['train_file_path'], model['train_file_name']):
            self.get_time_series_from_file(structure, model['name'], model['train_file_path'], model['train_file_name'])

        # Pretrain model with collected time series
        try:
            model['instance'].set_idle_consumption(self.idle_time_series[model['name']])
            model['instance'].pretrain(time_series=self.time_series[model['name']], data_type="df")

            log(f"Model using prediction method {model['prediction_method']} successfully pretrained using {model['train_file_name']} timestamps")

            # Plot train time series if specified
            if self.config.get_argument("plot_time_series"):
                output_dir = f"{self.config.get_argument('plot_time_series_dir')}/{structure}/{model['name']}/train"
                self.ts_plotter.set_output_dir(output_dir)
                log(f"Plotting train time series for model {model['name']}. Plot will be stored at {output_dir}")
                if model['hw_aware']:
                    sockets = self.config.get_argument('sockets')
                    # Create a plot for each submodel (2 running models + 2 active models)
                    for i in range(sockets):
                        current_cpu = f"CPU{i}"
                        next_cpu_num = (i + 1) % sockets
                        next_cpu = f"CPU{next_cpu_num}"
                        cpu_mask = self.time_series[model['name']]["exp_name"].str.startswith(current_cpu)
                        cpu_time_series = self.time_series[model['name']].loc[cpu_mask, :]
                        # Plot running model CPU i
                        self.ts_plotter.plot_time_series(f"{model['name']}_{current_cpu}_running_data",
                                                         cpu_time_series,
                                                         self.config.get_argument("model_variables"),
                                                         power_var=f"power_pkg{i}")
                        # Plot active model CPU (i + 1) % sockets
                        self.ts_plotter.plot_time_series(f"{model['name']}_{next_cpu}_active_data",
                                                         cpu_time_series,
                                                         self.config.get_argument("model_variables"),
                                                         power_var=f"power_pkg{next_cpu_num}")

                else:
                    self.ts_plotter.plot_time_series(f"{model['name']}_train_data",
                                                     self.time_series[model['name']],
                                                     self.config.get_argument("model_variables"))
                self.ts_plotter.plot_vars_vs_power(self.time_series[model['name']], self.config.get_argument("model_variables"))

        except Exception as e:
            log(f"{str(e)}", "ERR")

    def initialize_model(self, structure, model):
        model_variables = self.config.get_argument("model_variables")
        if model and model['instance']:
            model['instance'].set_model_vars(model_variables)
            if model['train_file_path']:
                self.pretrain_model(structure, model)

    @staticmethod
    def write_results(expected, predicted, output_dir, test_name):
        # TODO: Add more performance metrics
        mape = mean_absolute_percentage_error(expected, predicted)
        output_file = f"{output_dir}/results"
        with open(output_file, "a") as f:
            f.write(f"[{test_name}] MAPE: {mape}\n")

    def clean_test_dirs(self, base_dir):
        for structure in self.config.get_argument("structures"):
            for model_name in self.model_handler.get_models_by_structure(structure):
                model_dir = f"{base_dir}/{structure}/{model_name}/test/"
                if os.path.exists(model_dir) and os.path.isdir(model_dir):
                    for filename in os.listdir(model_dir):
                        file_path = os.path.join(model_dir, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                else:
                    os.makedirs(model_dir)

    def test_models(self):

        self.clean_test_dirs(self.config.get_argument('plot_time_series_dir'))
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
                    output_dir = f"{self.config.get_argument('plot_time_series_dir')}/{structure}/{model['name']}/test"

                    # Get predictions based on test data
                    new_time_series, power_predicted = model['instance'].test(time_series=test_time_series, data_type="df")
                    # Check if time series were modified during predictions
                    if new_time_series is not None:
                        test_time_series = new_time_series
                    test_time_series['power_predicted'] = power_predicted.flatten()

                    # Write results
                    self.write_results(test_time_series['power'], test_time_series['power_predicted'], output_dir, test_name)

                    # Plot results
                    if self.config.get_argument("plot_time_series"):
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

        # For each structure, prediction method and train file we try to create and initialize a model
        for structure in self.config.get_argument("structures"):
            self.ts_collector.set_structure(structure)
            self.clear_processed_files()
            for prediction_method in self.config.get_argument("prediction_methods"):
                for train_file in self.config.get_argument(f"train_files"):
                    train_file = None if train_file == "NPT" else train_file  # NPT = Not Pre-Trained

                    # Check that we always pretrain static methods
                    if train_file is None and ModelHandler.is_static_method(prediction_method):
                        log(f"Prediction method {prediction_method} doesn't support online learning, so it's mandatory "
                            f"to pretrain the model. Model {prediction_method}_NPT will be discarded", "WARN")
                        continue

                    # Check that we use the appropiate files for HW aware models
                    if ModelHandler.is_hw_aware_method(prediction_method):
                        # TODO: Add cores distribution and sockets from config
                        if self.is_hw_aware_compatible(train_file):
                            kwargs = {
                                "sockets": self.config.get_argument("sockets"),
                                "cores_distribution": self.config.get_argument("cores_distribution")
                            }
                            model = self.model_handler.add_model(structure, prediction_method, train_file, **kwargs)
                        else:
                            model_name = f"{prediction_method}_{ModelHandler.get_file_name(train_file)}"
                            log(f"Train file {train_file} is not suitable for HW aware models. This file must "
                                f"indicate the CPU socket where each experiment have been executed at the beginning of "
                                f"its <EXP_NAME> (e.g., CPU0_Group_P&L). Model {model_name} will be discarded", "WARN")
                            continue
                    else:
                        model = self.model_handler.add_model(structure, prediction_method, train_file)
                    self.initialize_model(structure, model)
        if self.model_handler.get_models():
            if len(self.config.get_argument("test_files")) > 0:
                self.test_models()
            else:
                log(f"The models won't be tested as no test files have been specified.", "WARN")
        else:
            log(f"No model has been created because no valid combination of prediction "
                f"method and training file has been found.", "ERR")
            exit(1)

import os
import shutil
import src.WattWizard.utils.utils as utils
from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler
from src.WattWizard.utils.ModelTrainer import ModelTrainer
from src.WattWizard.utils.ModelTester import ModelTester
from src.WattWizard.utils.DataLoader import DataLoader
from src.WattWizard.data.TimeSeriesPlotter import TimeSeriesPlotter


class ModelBuilder:

    def __init__(self):
        self.config = MyConfig.get_instance()
        self.model_handler = ModelHandler.get_instance()
        ts_plotter = TimeSeriesPlotter()
        data_loader = DataLoader(self.config)
        self.trainer = ModelTrainer(self.config, ts_plotter, data_loader)
        self.tester = ModelTester(self.config, ts_plotter, data_loader)

    def _clean_model_test_dir(self, structure, model):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    def _check_valid_combination(self, prediction_method, train_file):
        kwargs = {}
        reason = ""
        if not train_file and self.model_handler.is_static_method(prediction_method):
            reason = f"It's mandatory to pretrain static prediction method {prediction_method} (train file is None)"
            return False, reason, kwargs

        if self.model_handler.is_hw_aware_method(prediction_method):
            if train_file and utils.is_hw_aware_compatible(train_file):
                kwargs = {
                    "sockets": self.config.get_argument("sockets"),
                    "cores_distribution": self.config.get_argument("cores_distribution")
                }
            else:
                reason = f"Trying to train HW aware model with non-suitable file"
                return False, reason, kwargs

        return True, reason, kwargs

    def build_models(self):
        print(self.config.get_logo())
        for line in self.config.get_summary():
            log(line)
        models_to_test = []
        for structure in self.config.get_argument("structures"):
            for prediction_method in self.config.get_argument("prediction_methods"):
                for train_file in self.config.get_argument("train_files"):
                    # Check prediction method and train file combination is valid
                    valid, reason, kwargs = self._check_valid_combination(prediction_method, train_file)
                    if not valid:
                        log(f"Model discarded: {reason}", "WARN")
                        continue

                    # If combination is valid, create the model
                    model = self.model_handler.add_model(structure, prediction_method, train_file, **kwargs)

                    # If model was succesfully created and has a train file, train the model
                    if train_file and model.get('instance', None):
                        model['instance'].set_model_vars(self.config.get_argument("model_variables"))
                        self.trainer.pretrain_model(structure, model)

                        # If model is trained it can also be tested
                        models_to_test.append((structure, model))

        # If no model exists, there is nothing else to do
        if not self.model_handler.get_models():
            log("No valid model has been created. You need a suitable prediction_method-train_file combination", "ERR")
            exit(1)

        # Test models that have been previously trained
        for structure, model in models_to_test:
            self._clean_model_test_dir(structure, model)
            for test_file in self.config.get_argument("test_files"):
                self.tester.test_model(structure, model, test_file)

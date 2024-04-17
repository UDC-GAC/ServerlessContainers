import re

from src.WattWizard.model import *

STATIC_PREDICTION_METHODS = ["polyreg"]

INSTANCE_CONSTRUCTORS = {
    "mlpregressor": lambda: Perceptron(),
    "sgdregressor": lambda: SGDRegression(),
    "polyreg": lambda: PolynomialRegression()
}


class ModelHandler:
    __instance = None
    models = None

    @staticmethod
    def get_file_name(file):
        pattern = r'\/([^/]+)\.'
        occurrences = re.findall(pattern, file)
        return occurrences[-1]

    @staticmethod
    def get_instance():
        if ModelHandler.__instance is None:
            ModelHandler()
        return ModelHandler.__instance

    @staticmethod
    def create_model_instance(prediction_method):
        if prediction_method in INSTANCE_CONSTRUCTORS:
            return INSTANCE_CONSTRUCTORS[prediction_method]()
        raise Exception(f"Trying to create model with unsupported prediction method ({prediction_method})")

    @staticmethod
    def is_static(prediction_method):
        return prediction_method in STATIC_PREDICTION_METHODS

    def __init__(self):
        if ModelHandler.__instance is not None:
            raise Exception(f"Trying to break Singleton. There is already an instance of {self.__class__.__name__} class")
        else:
            ModelHandler.__instance = self

        self.models = {}

    def add_model(self, prediction_method, train_file):
        model_name = f"{prediction_method}_{self.get_file_name(train_file) if train_file else 'NPT'}"
        if model_name in self.models:
            raise Exception(f"Model with name {model_name} already exists")
        else:
            self.models[model_name] = {
                "prediction_method": prediction_method,
                "train_file": train_file,
                "instance": self.create_model_instance(prediction_method)
            }
        return model_name

    def get_models(self):
        return self.models

    def get_model_by_name(self, model_name):
        if model_name in self.models:
            return self.models[model_name]
        raise Exception(f'Model with name \'{model_name}\' doesn\'t exists')

    def __get_model_value(self, model_name, value):
        if model_name in self.models:
            if value in self.models[model_name]:
                return self.models[model_name][value]
            raise Exception(f"Attribute '{value}' doesn\'t exists for model {model_name}")
        raise Exception(f'Model with name \'{model_name}\' doesn\'t exists')

    def get_model_prediction_method(self, model_name):
        return self.__get_model_value(model_name, "prediction_method")

    def get_model_train_file(self, model_name):
        return self.__get_model_value(model_name, "train_file")

    def get_model_instance(self, model_name):
        return self.__get_model_value(model_name, "instance")

    def reset_model_instance(self, model_name):
        if model_name in self.models:
            self.models[model_name]["instance"] = self.create_model_instance(self.models[model_name]["prediction_method"])
        else:
            raise Exception(f'Model with name \'{model_name}\' doesn\'t exists')

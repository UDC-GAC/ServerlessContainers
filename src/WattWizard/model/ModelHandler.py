import os

from src.WattWizard.model import *
import src.WattWizard.utils.utils as utils

STATIC_PREDICTION_METHODS = ["polyreg", "interpolation", "multisocket", "randomforest", "arxmodel"]

HW_AWARE_PREDICTION_METHODS = ["multisocket"]

INSTANCE_CONSTRUCTORS = {
    "mlpregressor": lambda: Perceptron(),
    "sgdregressor": lambda: SGDRegression(),
    "polyreg": lambda: PolynomialRegression(),
    "multisocket": lambda **kwargs: MultiSocketRegresion(**kwargs),
    "segmentedreg": lambda: SegmentedRegression(),
    "interpolation": lambda: LinearInterpolation(),
    "randomforest": lambda: RandomForest(),
    "arxmodel": lambda: ARXModel()
}


class ModelHandler:
    __instance = None
    models = None

    @staticmethod
    def get_instance():
        if ModelHandler.__instance is None:
            ModelHandler()
        return ModelHandler.__instance

    @staticmethod
    def create_model_instance(prediction_method, **kwargs):
        if prediction_method in INSTANCE_CONSTRUCTORS:
            return INSTANCE_CONSTRUCTORS[prediction_method](**kwargs)
        raise Exception(f"Trying to create model with unsupported prediction method ({prediction_method})")

    @staticmethod
    def is_static_method(prediction_method):
        return prediction_method in STATIC_PREDICTION_METHODS

    @staticmethod
    def is_hw_aware_method(prediction_method):
        return prediction_method in HW_AWARE_PREDICTION_METHODS

    def __init__(self):
        if ModelHandler.__instance is not None:
            raise Exception(f"Trying to break Singleton. There is already an instance of {self.__class__.__name__} class")
        else:
            ModelHandler.__instance = self

        self.models = {}

    def add_model(self, structure, prediction_method, train_file, **kwargs):
        train_file_name = utils.get_file_name(train_file)
        model_name = f"{prediction_method}_{train_file_name}"
        if structure in self.models and model_name in self.models[structure]:
            raise Exception(f"Model with name {model_name} already exists")
        else:
            if structure not in self.models:
                self.models[structure] = {}
            self.models[structure][model_name] = {
                "name": model_name,
                "prediction_method": prediction_method,
                "train_file_path": train_file,
                "train_file_name": train_file_name,
                "instance": self.create_model_instance(prediction_method, **kwargs),
                "is_static": prediction_method in STATIC_PREDICTION_METHODS,
                "hw_aware": prediction_method in HW_AWARE_PREDICTION_METHODS
            }
        return self.models[structure][model_name]

    def get_model_names_by_structure(self, structure):
        if structure in self.models:
            return list(self.models[structure].keys())
        raise Exception(f"Structure {structure} doesn\'t exists")

    def get_non_static_model_names_by_structure(self, structure):
        if structure in self.models:
            return [model_name for model_name in self.models[structure] if not self.is_static(structure, model_name)]
        raise Exception(f"Structure {structure} doesn\'t exists")

    def get_model_names(self):
        models_dict = {}
        for structure in self.models:
            models_dict[structure] = self.get_model_names_by_structure(structure)
        return models_dict

    def get_non_static_model_names(self):
        models_dict = {}
        for structure in self.models:
            models_dict[structure] = self.get_non_static_model_names_by_structure(structure)
        return models_dict

    def get_models(self):
        return self.models

    def get_models_by_structure(self, structure):
        if structure in self.models:
            return self.models[structure]
        raise Exception(f"Structure {structure} doesn\'t exists")

    def get_host_models(self):
        self.get_models_by_structure("host")

    def get_container_models(self):
        self.get_models_by_structure("container")

    def get_model_by_name(self, structure, model_name):
        if structure in self.models and model_name in self.models[structure]:
            return self.models[structure][model_name]
        raise Exception(f'Model with name \'{model_name}\' for structure \'{structure}\' doesn\'t exists')

    def __get_model_value(self, structure, model_name, value):
        if structure in self.models:
            if model_name in self.models[structure]:
                if value in self.models[structure][model_name]:
                    return self.models[structure][model_name][value]
                raise Exception(f"Attribute '{value}' doesn\'t exists for model {model_name} and structure {structure}")
            raise Exception(f'Model with name \'{model_name}\' doesn\'t exists for structure {structure}')
        raise Exception(f'Structure \'{structure}\' doesn\'t exists')

    def get_model_prediction_method(self, structure, model_name):
        return self.__get_model_value(structure, model_name, "prediction_method")

    def get_model_train_file(self, structure, model_name):
        return self.__get_model_value(structure, model_name, "train_file")

    def get_model_instance(self, structure, model_name):
        return self.__get_model_value(structure, model_name, "instance")

    def is_static(self, structure, model_name):
        return self.__get_model_value(structure, model_name, "is_static")

    def is_hw_aware(self, structure, model_name):
        return self.__get_model_value(structure, model_name, "hw_aware")

    def reset_model_instance(self, structure, model_name):
        if structure in self.models and model_name in self.models[structure]:
            self.models[structure][model_name]["instance"] = self.create_model_instance(self.models[structure][model_name]["prediction_method"])
        else:
            raise Exception(f'Model with name \'{model_name}\' doesn\'t exists for structure \'{structure}\'')

from src.WattWizard.model import *
from src.WattWizard.config import config
from src.WattWizard.logs.logger import log


def run(model_name, pred_method=None):

    if pred_method == "mlpregressor":
        config.model_instances[model_name] = Perceptron()
    elif pred_method == "sgdregressor":
        config.model_instances[model_name] = SGDRegression()
    elif pred_method == "polyreg":
        config.model_instances[model_name] = PolynomialRegression() 
    else:
        log(f"Trying to restart model with unsupported prediction method ({pred_method})", "ERR")
        exit(1)
    
    model_instance = config.model_instances[model_name]
    model_instance.set_model_vars(config.model_vars)

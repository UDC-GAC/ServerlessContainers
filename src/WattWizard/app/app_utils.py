import numpy as np

from src.WattWizard.config.MyConfig import MyConfig

my_config = MyConfig.get_instance()

MODEL_VARIABLES_ARGS = ["current_X", "X_dict"]


def get_param_value(req, param, param_type=None):
    value = req.args.get(param, type=param_type)
    if value is None:
        raise TypeError(f"Missing {param} value in request. You must include it as follows"
                        f" <url>:<port>/predict?{param}=<value>")
    return value


def get_boolean_param_value(req, param):
    value = req.args.get(param, default='')
    return value == "true"


def get_model_variables_from_request(model_vars, request):
    x_values = {}
    for var in model_vars:
        x_values[var] = get_param_value(request, var, param_type=float)
    return x_values


def get_kwargs_from_request(model_instance, request, method):
    required_kwargs = model_instance.get_required_kwargs(method)
    kwargs_dict = {}
    for arg in required_kwargs:
        if arg in MODEL_VARIABLES_ARGS:
            kwargs_dict[arg] = get_model_variables_from_request(model_instance.get_model_vars(), request)
        else:
            kwargs_dict[arg] = get_param_value(request, arg)

    return kwargs_dict

import numpy as np

from src.WattWizard.config.MyConfig import MyConfig

my_config = MyConfig.get_instance()


def get_param_value(req, param, param_type=None):
    value = req.args.get(param, type=param_type)
    if value is None:
        raise TypeError(f"Missing {param} value in request. You must include it as follows"
                        f" <url>:<port>/predict?{param}=<value>")
    return value


def get_boolean_param_value(req, param):
    value = req.args.get(param, default='')
    return value == "true"


def get_model_variables_from_request(model_instance, request):
    x_values = {}
    for var in model_instance.get_model_vars():
        value = request.args.get(var, type=float)
        if value is not None:
            x_values[var] = value
        else:
            raise TypeError(f"Missing {var} value in request. You must include it as follows"
                            f" <url>:<port>/predict?{var}=<value>")
    return x_values

from flask import Blueprint
from flask import jsonify
from flask import request

from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler
from src.WattWizard.app.app_utils import get_param_value, get_boolean_param_value, get_kwargs_from_request

DYNAMIC_VAR = "user_load"

routes = Blueprint('routes', __name__)
my_config = MyConfig.get_instance()
model_handler = ModelHandler.get_instance()


@routes.route('/is-static/<structure>/<model_name>', methods=['GET'])
def is_static(structure=None, model_name=None):
    try:
        return jsonify({'is_static': model_handler.is_static(structure, model_name)})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/is-hw-aware/<structure>/<model_name>', methods=['GET'])
def is_hw_aware(structure=None, model_name=None):
    try:
        return jsonify({'is_hw_aware': model_handler.is_hw_aware(structure, model_name)})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


# Potential improvement: Remove idle consumption route and implement logic on predict
# When utilization is below 100% (bad predictions) power can be computed as follows:
# P = idle + (user+system)% * (prediction(100%) - idle)
@routes.route('/predict/<structure>/<model_name>', methods=['GET'])
def predict_power(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        kwargs = get_kwargs_from_request(model_instance, request, 'predict')
        my_config.check_resources_limits(kwargs['X_dict'])
        predicted_consumption = model_instance.predict(**kwargs)
        return jsonify({'predicted_power': predicted_consumption})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/inverse-predict/<structure>/<model_name>', methods=['GET'])
def predict_values_from_power(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        kwargs = get_kwargs_from_request(model_instance, request, 'get_inverse_prediction')
        if 'X_dict' in kwargs:
            my_config.check_resources_limits(kwargs['X_dict'])
        desired_power = get_param_value(request, "desired_power", float)
        dynamic_var = get_param_value(request, "dynamic_var")
        var_limits = my_config.get_resource_cpu_limits(dynamic_var)
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption and desired_power <= idle_consumption:
            return jsonify({'ERROR': f'Requested power value ({desired_power}) lower than idle consumption ({idle_consumption})'}), 400
        result = model_instance.get_inverse_prediction(desired_power, dynamic_var, var_limits, **kwargs)
        return jsonify(result)
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/adjusted-inverse-predict/<structure>/<model_name>', methods=['GET'])
def predict_adjusted_values_from_power(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        kwargs = get_kwargs_from_request(model_instance, request, 'get_adjusted_inverse_prediction')
        if 'X_dict' in kwargs:
            my_config.check_resources_limits(kwargs['X_dict'])
        real_power = get_param_value(request, "real_power", float)
        desired_power = get_param_value(request, "desired_power", float)
        dynamic_var = get_param_value(request, "dynamic_var")
        var_limits = my_config.get_resource_cpu_limits(dynamic_var)
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption and desired_power <= idle_consumption:
            return jsonify({'ERROR': f'Requested power value ({desired_power}) lower than idle consumption ({idle_consumption})'}), 400

        result = model_instance.get_adjusted_inverse_prediction(real_power, desired_power, dynamic_var, var_limits, **kwargs)
        return jsonify(result)
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/idle-consumption/<structure>/<model_name>', methods=['GET'])
def predict_idle(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption is not None:
            return jsonify({'idle_consumption': idle_consumption})
        else:
            return jsonify({'ERROR': f'Model {model_name} not pretrained. Separate values for idle consumption are only inferred from pretrain data'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/models', methods=['GET'])
def get_available_models():
    try:
        avoid_static = get_boolean_param_value(request, "avoid-static")
        if avoid_static:
            return jsonify(model_handler.get_non_static_model_names())
        return jsonify(model_handler.get_model_names())
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/models/<structure>', methods=['GET'])
def get_available_models_structure(structure=None):
    try:
        avoid_static = get_boolean_param_value(request, "avoid-static")
        if avoid_static:
            return jsonify(model_handler.get_non_static_model_names_by_structure(structure))
        return jsonify(model_handler.get_model_names_by_structure(structure))
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/model-attributes/<structure>/<model_name>', methods=['GET'])
def get_model_attributes(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        coefs = model_instance.get_coefs()
        intercept = model_instance.get_intercept()
        if intercept is None or coefs is None:
            return jsonify({'ERROR': 'Model not trained. Train the model first, then you could get its attributes'}), 400
        else:
            return jsonify({'intercept': intercept, 'coefficients': coefs})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400

@routes.route('/model-variables/<structure>/<model_name>', methods=['GET'])
def get_model_variables(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        model_variables = model_instance.get_model_vars
        if model_variables is None:
            return jsonify({'ERROR': 'Model doesn\'t have variables. Something weird has happened.'}), 400
        else:
            return jsonify({'model_variables': model_variables})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits', methods=['GET'])
def get_cpu_limits():
    try:
        return jsonify(my_config.get_cpu_limits())
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits/<var>', methods=['GET'])
def get_cpu_limits_from_var(var=None):
    try:
        return my_config.get_resource_cpu_limits(var)
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits', methods=['PUT'])
def set_cpu_limits():
    try:
        json_data = eval(request.json) if isinstance(request.json, str) else request.json
        for var in json_data:
            if "max" in json_data[var]:
                my_config.set_resource_cpu_limit(var, "max", json_data[var]["max"])
            if "min" in json_data[var]:
                my_config.set_resource_cpu_limit(var, "min", json_data[var]["min"])
        return jsonify({'INFO': 'CPU limits successfully updated'})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/train/<structure>/<model_name>', methods=['POST'])
def train_model(structure=None, model_name=None):
    json_data = eval(request.json) if isinstance(request.json, str) else request.json
    try:
        model = model_handler.get_model_by_name(structure, model_name)
        if not model_handler.is_static(structure, model_name):
            model["instance"].train(time_series=json_data, data_type="json")
            return jsonify({'INFO': f'Model trained successfully (Train {model["instance"].get_times_trained()})'})
        else:
            return jsonify({'ERROR': f'Model {model_name} using static method {model["prediction_method"]} '
                                     f'which doesn\'t support online learning'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/reset-model/<structure>/<model_name>', methods=['DELETE'])
def reset_model(structure=None, model_name=None):
    try:
        if not model_handler.is_static(structure, model_name):
            model_handler.reset_model_instance(structure, model_name)
            model_instance = model_handler.get_model_instance(structure, model_name)
            model_instance.set_model_vars(my_config.get_argument("model_variables"))
            return jsonify({'INFO': 'Model successfully restarted'}), 200
        else:
            return jsonify({'ERROR': f'Model \'{model_name}\' using static method can\'t be restarted'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400

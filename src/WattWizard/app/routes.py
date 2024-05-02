from flask import Blueprint
from flask import jsonify
from flask import request

from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.model.ModelHandler import ModelHandler
from src.WattWizard.app.app_utils import get_desired_power, json_to_train_data, request_to_dict

DYNAMIC_VAR = "user_load"

routes = Blueprint('routes', __name__)
my_config = MyConfig.get_instance()
model_handler = ModelHandler.get_instance()


@routes.route('/is-static/<structure>/<model_name>', methods=['GET'])
def is_static(structure=None, model_name=None):
    try:
        prediction_method = model_handler.get_model_prediction_method(structure, model_name)
        return jsonify({'is_static': ModelHandler.is_static(prediction_method)})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400

# Potential improvement: Remove idle consumption route and implement logic on predict
# When utilization is below 100% (bad predictions) power can be computed as follows:
# P = idle + (user+system)% * (prediction(100%) - idle)
@routes.route('/predict/<structure>/<model_name>', methods=['GET'])
def predict_power(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        X_test = request_to_dict(model_instance, request)
        my_config.check_resources_limits(X_test)
        predicted_consumption = model_instance.predict(X_test)
        return jsonify({'predicted_power': predicted_consumption})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/inverse-predict/<structure>/<model_name>', methods=['GET'])
def predict_values_from_power(structure=None, model_name=None):
    try:
        model_instance = model_handler.get_model_instance(structure, model_name)
        current_X = request_to_dict(model_instance, request)

        my_config.check_resources_limits(current_X)
        var_limits = my_config.get_resource_cpu_limits(DYNAMIC_VAR)

        desired_power = get_desired_power(request)
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption and desired_power <= idle_consumption:
            return jsonify({'ERROR': f'Requested power value ({desired_power}) lower than idle consumption ({idle_consumption})'}), 400

        result = model_instance.get_inverse_prediction(current_X, desired_power, DYNAMIC_VAR, var_limits)
        return jsonify({DYNAMIC_VAR: result})
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
        return jsonify(model_handler.get_model_names())
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/models/<structure>', methods=['GET'])
def get_available_models_structure(structure=None):
    try:
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


@routes.route('/cpu-limits', methods=['GET'])
def get_cpu_limits():
    try:
        return jsonify(my_config.get_cpu_limits())
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits/<var>', methods=['GET'])
def get_cpu_limits_from_var(var=None):
    try:
        my_config.get_resource_cpu_limits(var)
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
        if not ModelHandler.is_static(model["prediction_method"]):
            X_train, y_train = json_to_train_data(model["instance"], json_data)
            model["instance"].train(X_train, y_train)
            return jsonify({'INFO': f'Model trained successfully (Train {model["instance"].get_times_trained()})'})
        else:
            return jsonify({'ERROR': f'Model {model_name} using static method {model["prediction_method"]} '
                                     f'which doesn\'t support online learning'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/reset-model/<structure>/<model_name>', methods=['DELETE'])
def reset_model(structure=None, model_name=None):
    try:
        prediction_method = model_handler.get_model_prediction_method(structure, model_name)
        if not ModelHandler.is_static(prediction_method):
            model_handler.reset_model_instance(structure, model_name)
            model_instance = model_handler.get_model_instance(structure, model_name)
            model_instance.set_model_vars(my_config.get_argument("model_variables"))
            return jsonify({'INFO': 'Model successfully restarted'}), 200
        else:
            return jsonify({'ERROR': f'Model \'{model_name}\' using static method '
                                     f'\'{prediction_method}\' can\'t be restarted'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400

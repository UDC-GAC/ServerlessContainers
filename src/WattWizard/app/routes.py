from flask import Blueprint
from flask import jsonify
from flask import request

from src.WattWizard.config import config
from src.WattWizard.utils import reset_model
from src.WattWizard.app.model_operations import check_model_exists, get_pred_method, get_desired_power, json_to_train_data, request_to_dict, get_inverse_prediction

routes = Blueprint('routes', __name__)


# Potential improvement: Remove idle consumption route and implement logic on predict
# When utilization is below 100% (bad predictions) power can be computed as follows:
# P = idle + (user+system)% * (prediction(100%) - idle)
@routes.route('/predict/<model_name>', methods=['GET'])
def predict_power(model_name=None):
    try:
        check_model_exists(model_name)
        model_instance = config.model_instances[model_name]
        X_test = request_to_dict(model_instance, request)
        predicted_consumption = model_instance.predict(X_test)
        return jsonify({'predicted_power': predicted_consumption})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/inverse-predict/<model_name>', methods=['GET'])
def predict_values_from_power(model_name=None):
    try:
        dynamic_var = "user_load"  # Hardcoded
        check_model_exists(model_name)
        model_instance = config.model_instances[model_name]
        current_X = request_to_dict(model_instance, request)
        desired_power = get_desired_power(request)
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption and desired_power <= idle_consumption:
            return jsonify({'ERROR': f'Requested power value ({desired_power}) lower than idle consumption ({idle_consumption})'}), 400
        dynamic_value = get_inverse_prediction(model_instance, current_X, desired_power, dynamic_var)
        return jsonify({dynamic_var: dynamic_value})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/idle-consumption/<model_name>', methods=['GET'])
def predict_idle(model_name=None):
    try:
        check_model_exists(model_name)
        model_instance = config.model_instances[model_name]
        idle_consumption = model_instance.get_idle_consumption()
        if idle_consumption is not None:
            return jsonify({'idle_consumption': idle_consumption})
        else:
            return jsonify({'ERROR': f'Model {model_name} not pretrained. Separate values for idle consumption are only inferred from pretrain data'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/model-attributes/<model_name>', methods=['GET'])
def get_model_attributes(model_name=None):
    try:
        check_model_exists(model_name)
        model_instance = config.model_instances[model_name]
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
        return jsonify(config.cpu_limits)
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits/<var>', methods=['GET'])
def get_cpu_limits_from_var(var=None):
    try:
        if var in config.cpu_limits:
            return jsonify(config.cpu_limits[var])
        else:
            return jsonify({'ERROR': f'CPU limits requested from a non-existent variable {var}'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/cpu-limits', methods=['PUT'])
def set_cpu_limits():
    try:
        json_data = request.json
        for var in json_data:
            if "max" in json_data[var]:
                config.cpu_limits[var]["max"] = json_data[var]["max"]
            if "min" in json_data[var]:
                config.cpu_limits[var]["min"] = json_data[var]["min"]
        return jsonify({'INFO': 'CPU limits successfully updated'})
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/train/<model_name>', methods=['POST'])
def train_model(model_name=None):
    json_data = request.json
    try:
        check_model_exists(model_name)
        pred_method = get_pred_method(model_name)
        if pred_method not in config.STATIC_METHODS:
            model_instance = config.model_instances[model_name]
            X_train, y_train = json_to_train_data(model_instance, json_data)
            model_instance.train(X_train, y_train)
            return jsonify({'INFO': f'Model trained successfully (Train {model_instance.get_times_trained()})'})
        else:
            return jsonify({'ERROR': f'Model {model_name} using static method {pred_method} which doesn\'t support online learning'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400


@routes.route('/restart-model/<model_name>', methods=['DELETE'])
def restart_model(model_name=None):
    try:
        check_model_exists(model_name)
        pred_method = get_pred_method(model_name)
        if pred_method not in config.STATIC_METHODS:
            reset_model.run(model_name, pred_method)
            return jsonify({'INFO': 'Model successfully restarted'}), 200
        else:
            return jsonify({'ERROR': f'Model {model_name} using static method {pred_method} can\'t be restarted'}), 400
    except Exception as e:
        return jsonify({'ERROR': str(e)}), 400
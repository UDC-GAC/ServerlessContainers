MAX_ERROR = 0.001
MAX_ITERS = 100


class Model(object):

    model_vars = None
    times_trained = None
    pretrained = None
    idle_consumption = None

    def __init__(self):
        self.model_vars = []
        self.times_trained = 0
        self.pretrained = False
        self.idle_consumption = 0

    def get_times_trained(self):
        return self.times_trained

    def get_model_vars(self):
        return self.model_vars
    
    def get_idle_consumption(self):
        return self.idle_consumption if self.pretrained else None

    def set_model_vars(self, v):
        self.model_vars = v
    
    def set_idle_consumption(self, v):
        self.idle_consumption = v
    
    def is_fitted(self, attr_name):
        estimator = getattr(self, attr_name, None)
        return hasattr(estimator, 'n_features_in_')

    def get_inverse_prediction(self, current_X, desired_power, dynamic_var, limits):
        estimated_power = self.predict(current_X)
        error = abs(desired_power - estimated_power)
        count_iters = 0
        while error > MAX_ERROR and count_iters < MAX_ITERS and limits["min"] < current_X[dynamic_var] < limits["max"]:
            current_X[dynamic_var] = desired_power * current_X[dynamic_var] / estimated_power
            estimated_power = self.predict(current_X)
            error = abs(desired_power - estimated_power)
            count_iters += 1

        return {
            "value": max(limits["min"], min(limits["max"], current_X[dynamic_var]))
        }

    def get_adjusted_inverse_prediction(self, current_X, real_power, desired_power, dynamic_var, limits):
        result = self.get_inverse_prediction(current_X, desired_power, dynamic_var, limits)
        # Adjust estimation based on model error
        result["model_error_percentage"] = (self.predict(current_X) - real_power) / max(real_power, float('1e-30'))
        adjusted_value = result["value"] * (1 + result["model_error_percentage"])
        result["adjusted_value"] = max(limits["min"], min(limits["max"], adjusted_value))
        return result

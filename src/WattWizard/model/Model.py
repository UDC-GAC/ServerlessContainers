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
        current_power = self.predict(current_X)
        error = abs(desired_power - current_power)
        count_iters = 0
        while error > MAX_ERROR and count_iters < MAX_ITERS and limits["min"] < current_X[dynamic_var] < limits["max"]:
            current_X[dynamic_var] = desired_power * current_X[dynamic_var] / current_power
            current_power = self.predict(current_X)
            error = abs(desired_power - current_power)
            count_iters += 1

        value = limits["max"] if current_X[dynamic_var] > limits["max"] else current_X[dynamic_var]
        value = limits["min"] if value < limits["min"] else current_X[dynamic_var]
        return value

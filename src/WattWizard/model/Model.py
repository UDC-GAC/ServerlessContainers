import numpy as np

MAX_ERROR = 0.001
MAX_ITERS = 100


class Model(object):

    model_vars = None
    times_trained = None
    pretrained = None
    idle_consumption = None
    required_kwargs_map = None

    def __init__(self):
        self.model_vars = []
        self.times_trained = 0
        self.pretrained = False
        self.idle_consumption = 0
        self.required_kwargs_map = {
            "get_inverse_prediction": ["X_dict"],
            "get_adjusted_inverse_prediction": ["X_dict"]
        }

    @staticmethod
    def check_required_kwargs(required_args, kwargs):
        for arg in required_args:
            if arg not in kwargs:
                raise TypeError(f"Missing 1 required positional argument '{arg}'")

    def get_required_kwargs(self, method):
        return self.required_kwargs_map.get(method, [])

    def get_times_trained(self):
        return self.times_trained

    def get_model_vars(self):
        return self.model_vars
    
    def get_idle_consumption(self):
        return self.idle_consumption if self.pretrained else None

    def set_model_vars(self, v):
        self.model_vars = v
    
    def set_idle_consumption(self, time_series):
        if "power" not in time_series:
            raise TypeError("Missing power in idle time series while setting idle consumption")
        self.idle_consumption = time_series["power"].mean()

    def is_fitted(self, attr_name):
        estimator = getattr(self, attr_name, None)
        return hasattr(estimator, 'n_features_in_')

    def df_to_model_data(self, df, *args, **kwargs):
        x_values = []
        for var in self.model_vars:
            if var in df:
                x_values.append(df[var].values.reshape(-1, 1))
            else:
                raise TypeError(f"Missing variable {var} in DataFrame")
        x_stack = np.hstack(x_values)
        if "power" in df:
            y = df["power"].values
        else:
            raise TypeError("Missing power data in DataFrame")
        return x_stack, y

    def json_to_model_data(self, json_data, *args, **kwargs):
        x_values = []
        for var in self.model_vars:
            if var not in json_data:
                raise TypeError(f"Missing {var} data in JSON")
            x_values.append(np.array(json_data[var]).reshape(-1, 1))
        x_stack = np.hstack(x_values)

        if "power" in json_data:
            y = np.array(json_data["power"])
        else:
            raise TypeError("Missing power data in JSON")

        return x_stack, y

    def get_model_data(self, time_series, data_type):
        if data_type == "df":
            return self.df_to_model_data(time_series)
        elif data_type == "json":
            return self.json_to_model_data(time_series)
        else:
            raise TypeError(f"Not supported data type {data_type}. It must be DataFrame or JSON.")

    def get_inverse_prediction(self, desired_power, dynamic_var, limits, **kwargs):
        estimated_power = self.predict(**kwargs)
        error = abs(desired_power - estimated_power)
        count_iters = 0
        while error > MAX_ERROR and count_iters < MAX_ITERS and limits["min"] < kwargs['X_dict'][dynamic_var] < limits["max"]:
            kwargs['X_dict'][dynamic_var] = desired_power * kwargs['X_dict'][dynamic_var] / estimated_power
            estimated_power = self.predict(**kwargs)
            error = abs(desired_power - estimated_power)
            count_iters += 1

        return {
            "value": max(limits["min"], min(limits["max"], kwargs['X_dict'][dynamic_var]))
        }

    def get_adjusted_inverse_prediction(self, real_power, desired_power, dynamic_var, limits, **kwargs):
        result = self.get_inverse_prediction(desired_power, dynamic_var, limits, **kwargs)
        # Adjust estimation based on model error
        result["model_error_percentage"] = (self.predict(**kwargs) - real_power) / max(real_power, float('1e-30'))
        adjusted_value = result["value"] * (1 + result["model_error_percentage"])
        result["adjusted_value"] = max(limits["min"], min(limits["max"], adjusted_value))
        return result

    ########################################################################################################
    #   MODEL DEPENDENT METHODS - Implement at least these methods  and __init__ to create a new model     #
    ########################################################################################################

    def get_coefs(self):
        print("Get model coefficients or weights")

    def get_intercept(self):
        print("Get model intercept or constant term if it exists")

    def pretrain(self, *args, **kwargs):
        print("This method is responsible for the initial training of the model")

    def train(self, *args, **kwargs):
        print("This method is responsible for the online training of the model, that is, "
              "to train the model as new data arrives")

    def test(self, *args, **kwargs):
        print("This method is responsible for testing the model with a dataset in order to know its accuracy")

    def predict(self, *args, **kwargs):
        print("This method is responsible for obtaining a prediction from a dictionary that "
              "contains a value for each model variable")

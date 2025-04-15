import numpy as np
from sklearn.linear_model import LinearRegression

from src.WattWizard.model.Model import Model


#################################################################################################################
# AutoRegressive with eXogenous input (ARX) model:
#
# General form:
#   y(k+lag) = a1*y(k) + a2*y(k+1) + ... + an*y(k+lag-1) + b1*x(k) + b2*x(k+1) + ... + bn*x(k+lag-1)
#
# It can also be represented as:
#   y(k) = a1*y(k-1) + a2*y(k-2) + ... + an*y(k-lag) + b1*x(k-1) + b2*x(k-2) + ... + bn*x(k-lag)
#################################################################################################################
class ARXModel(Model):

    model = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.model = LinearRegression(fit_intercept=False)
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": None,
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })
        self.lag = 1

    def get_model_vars(self):
        # Power is also a variable in autoregressive models
        if self.lag > 1:
            return [f"{var}_{lag}" for lag in range(0, self.lag) for var in self.model_vars + ["power"]]
        return self.model_vars + ["power"]

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.coef_.tolist()
        return None

    def get_intercept(self):
        return self.idle_consumption

    def _lag_input_features(self, X, y):
        # Add all x values from x(k) to x(k+lag-1) and y values from y(k) to y(k+lag-1)
        x_values = []
        for i in range(0, self.lag):
            x_values.append(X[i:-(self.lag-i)])     # x(k+i)
            x_values.append(y[i:-(self.lag-i)])     # y(k+i)
        return np.hstack(x_values)

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)

        if kwargs['data_type'] != "df":
            raise TypeError(f"Model {self.__class__.__name__} only supports DataFrame time series")

        # Sort time series by time
        kwargs['time_series'].sort_values(by=["time_diff"], inplace=True)

        # Get data properly formatted
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])

        # Remove idle consumption (predict only active consumption)
        y_adjusted = y_train - self.idle_consumption

        # Add lagged x and y values to train data
        X_train = self._lag_input_features(X_train, y_adjusted.reshape(-1, 1))

        # Set y(k+lag) as y(k)
        y_adjusted = y_adjusted[self.lag:]

        self.model.fit(X_train, y_adjusted)
        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")

        if kwargs['data_type'] != "df":
            raise TypeError(f"Model {self.__class__.__name__} only supports DataFrame time series")

        # Sort time series by time
        kwargs['time_series'].sort_values(by=["time_diff"], inplace=True)

        # Get data properly formatted
        X_test, y_test = self.get_model_data(kwargs['time_series'], kwargs['data_type'])

        # Remove idle consumption (predict only active consumption)
        y_adjusted = y_test - self.idle_consumption

        # Add lagged x and y values to test data
        X_test = self._lag_input_features(X_test, y_adjusted.reshape(-1, 1))

        # Get predictions
        y_pred = self.idle_consumption + self.model.predict(X_test)

        # Insert the actual value in the first <lag> positions, as first prediction is y(k+lag) (value in the <lag> position)
        for i in range(0, self.lag):
            y_pred = np.insert(y_pred, i, y_test[i])

        return kwargs['time_series'], y_pred

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_values = [[kwargs['X_dict'][var] - self.idle_consumption if var.startswith("power") else kwargs['X_dict'][var]
                    for var in self.get_model_vars()]]
        return self.idle_consumption + self.model.predict(X_values)[0]

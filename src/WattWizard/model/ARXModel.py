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
        self.x_offset, self.y_offset = None, None
        self.x_degree, self.y_degree = 1, 1
        self.x_lag, self.y_lag = 1, 1
        self.max_lag = max(self.x_lag, self.y_lag)

    def get_model_vars(self):
        ylags = [f"power(k-{i})^{d}" for i in range(1, self.y_lag + 1) for d in range(1, self.y_degree + 1)]
        xlags = [f"{var}(k-{i})^{d}" for i in range(1, self.x_lag + 1) for d in range(1, self.x_degree + 1) for var in self.model_vars]
        return ylags + xlags

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.coef_.tolist()
        return None

    def get_intercept(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.intercept_

    def _lag_input_features(self, X, y):
        # Add all x values from x(k-1) to x(k-x_lag) and y values from y(k-1) to y(k-y_lag)
        x_values = []
        # Append y(k-1) to y(k-y_lag)
        for i in range(1, self.y_lag+1):
            for d in range(1, self.y_degree + 1):
                x_values.append(y[(self.max_lag - i):-i] ** d)       # y(k-i)^d

        # Append x(k-1) to x(k-y_lag)
        for i in range(1, self.x_lag+1):
            for d in range(1, self.x_degree + 1):
                x_values.append(X[(self.max_lag - i):-i] ** d)       # x(k-i)^d

        return np.hstack(x_values)

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)

        if kwargs['data_type'] != "df":
            raise TypeError(f"Model {self.__class__.__name__} only supports DataFrame time series")

        # Sort time series by time
        kwargs['time_series'].sort_values(by=["time_diff"], inplace=True)

        # Get data properly formatted
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])

        self.x_offset = np.mean(X_train, axis=0)
        self.y_offset = np.mean(y_train)

        X_centered = X_train - self.x_offset
        y_centered = y_train - self.y_offset

        # Add lagged x and y values to train data
        X_lagged = self._lag_input_features(X_centered, y_centered.reshape(-1, 1))

        # Set y(k+lag) as y(k)
        y_lagged = y_centered[self.max_lag:]

        self.model.fit(X_lagged, y_lagged)
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

        X_centered = X_test - self.x_offset
        y_centered = y_test - self.y_offset

        # Add lagged x and y values to test data
        X_lagged = self._lag_input_features(X_centered, y_centered.reshape(-1, 1))

        # Get predictions
        y_pred = self.model.predict(X_lagged) + self.y_offset

        # Insert the actual value in the first max_lag positions, as first max_lag test values are used as input data
        for i in range(0, self.max_lag):
            y_pred = np.insert(y_pred, i, y_test[i])

        return kwargs['time_series'], y_pred

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_values = [[(kwargs['X_dict'][f"{var}(k-{i})"] ** d) - self.x_offset
                     for i in range(1, self.x_lag + 1) for d in range(1, self.x_degree + 1) for var in self.model_vars]]
        return self.model.predict(X_values)[0] + self.y_offset

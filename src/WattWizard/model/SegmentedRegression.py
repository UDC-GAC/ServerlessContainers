import numpy as np

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model


class SegmentedRegression(Model):

    model = None


    def __init__(self, *args, **kwargs):
        super().__init__()
        self.threshold = 200
        self.var_threshold = 'user_load'
        self.models = {
            "low": LinearRegression(fit_intercept=False),
            "high": LinearRegression(fit_intercept=False)
        }
        self.poly_features = {
            "low": PolynomialFeatures(degree=2, include_bias=False),
            "high": PolynomialFeatures(degree=2, include_bias=False)
        }
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": None,
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            coefs_list = []
            for section in self.models:
                coefs_list.append(self.models[section].coef_.tolist())
            return coefs_list
        return None

    def get_intercept(self):
        return self.idle_consumption

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)

        time_series = {
            "low": kwargs['time_series'][kwargs['time_series'][self.var_threshold] < self.threshold],
            "high": kwargs['time_series'][kwargs['time_series'][self.var_threshold] >= self.threshold]
        }

        for section in ["low", "high"]:
            X_train, y_train = self.get_model_data(time_series[section], kwargs['data_type'])
            X_poly = self.poly_features[section].fit_transform(X_train)
            y_adjusted = y_train - self.idle_consumption
            self.models[section].fit(X_poly, y_adjusted)
        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")

        time_series = {
            "low": kwargs['time_series'][kwargs['time_series'][self.var_threshold] < self.threshold],
            "high": kwargs['time_series'][kwargs['time_series'][self.var_threshold] >= self.threshold]
        }

        predictions = []
        for section in ["low", "high"]:
            X_test, y_test = self.get_model_data(time_series[section], kwargs['data_type'])
            if len(X_test) > 0:
                X_poly = self.poly_features[section].transform(X_test)
                predictions.append(self.models[section].predict(X_poly) + self.idle_consumption)

        return None, np.concatenate(predictions)

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        section = "low" if kwargs['X_dict'][self.var_threshold] < self.threshold else "high"
        X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
        X_poly = self.poly_features[section].transform(X_values)
        return self.idle_consumption + self.models[section].predict(X_poly)[0]

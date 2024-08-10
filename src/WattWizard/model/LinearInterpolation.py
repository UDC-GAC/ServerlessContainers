import numpy as np

import pandas as pd
from scipy.interpolate import griddata
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model

class LinearInterpolation(Model):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.bin_size = 50
        self.points = None
        self.values = None
        self.griddata_method = 'linear'
        self.aux_model = LinearRegression(fit_intercept=False)
        self.poly_features = PolynomialFeatures(degree=4, include_bias=False)
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": None,
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })

    def get_coefs(self):
        return None

    def get_intercept(self):
        return self.idle_consumption

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)
        X_train = kwargs['time_series'][self.model_vars + ["power"]]
        X_train.loc[:, "power"] = X_train["power"] - self.idle_consumption
        bins = [np.arange(X_train[var].min(), X_train[var].max() + self.bin_size, self.bin_size) for var in self.model_vars]
        grouped = X_train.groupby([pd.cut(X_train[var], bins[i]) for i, var in enumerate(self.model_vars)]).mean()
        self.points = grouped[self.model_vars].dropna().values
        self.values = grouped["power"].dropna().values

        X_train_poly = self.poly_features.fit_transform(X_train[self.model_vars])
        self.aux_model.fit(X_train_poly, X_train["power"])

        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_test = kwargs['time_series'][self.model_vars]
        y_pred = griddata(self.points, self.values, X_test, method=self.griddata_method, fill_value=np.nan)

        nan_indices = np.isnan(y_pred)
        if nan_indices.any():
            X_test_poly = self.poly_features.transform(X_test[nan_indices])
            y_pred[nan_indices] = self.aux_model.predict(X_test_poly)
        return self.idle_consumption + y_pred

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_values = np.array([[kwargs['X_dict'][var] for var in self.model_vars]])
        y_pred = griddata(self.points, self.values, X_values, method=self.griddata_method)
        value = y_pred[0][0]
        if np.isnan(y_pred).any():
            X_values_poly = self.poly_features.transform([[kwargs['X_dict'][var] for var in self.model_vars]])
            y_pred = self.aux_model.predict(X_values_poly)
            value = y_pred[0]
        return self.idle_consumption + value

import numpy as np
from sklearn.linear_model import SGDRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from src.WattWizard.model.Model import Model

NEW_DATA_WEIGHT_DIFF = 0  # 0.1 means each new microbatch has 10% more weight than older data


class SGDRegression(Model):

    model = None
    pipeline = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.model = SGDRegressor(eta0=0.001, learning_rate="constant", max_iter=10000)
        self.pipeline = Pipeline(steps=[
            ('preprocessor', PolynomialFeatures(degree=2)),
            ('scaler', StandardScaler())
        ])
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": ['time_series', 'data_type'],
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.coef_.tolist()
        return None

    def get_intercept(self):
        return self.idle_consumption

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        X_scaled = self.pipeline.fit_transform(X_train)
        y_adjusted = y_train - self.idle_consumption
        self.model.fit(X_scaled, y_adjusted)
        self.pretrained = True

    def train(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['train'], kwargs)
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        if not self.is_fitted('pipeline'):
            self.pipeline.fit(X_train)
        X_scaled = self.pipeline.transform(X_train)
        y_adjusted = y_train - self.idle_consumption
        weights = np.ones(len(y_train)) + self.times_trained * NEW_DATA_WEIGHT_DIFF
        self.model.partial_fit(X_scaled, y_adjusted, sample_weight=weights)
        self.times_trained += 1

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        X_test, y_test = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        if not self.is_fitted('pipeline'):
            self.pipeline.fit(X_test)
        X_scaled = self.pipeline.transform(X_test)
        return self.model.predict(X_scaled) + self.idle_consumption

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
        if not self.is_fitted('pipeline'):
            self.pipeline.fit(X_values)
        X_scaled = self.pipeline.transform(X_values)
        return self.model.predict(X_scaled)[0] + self.idle_consumption

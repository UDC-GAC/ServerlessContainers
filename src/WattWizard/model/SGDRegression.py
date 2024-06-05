import numpy as np
from sklearn.linear_model import SGDRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from src.WattWizard.model.Model import Model

NEW_DATA_WEIGHT_DIFF=0 # 0.1 means each new microbatch has 10% more weight than older data

class SGDRegression(Model):

    model = None
    pipeline = None

    def __init__(self):
        super().__init__()
        self.model = SGDRegressor(eta0=0.001, learning_rate="constant", max_iter=1000)
        self.pipeline = Pipeline(steps=[
            ('preprocessor', PolynomialFeatures(degree=2)),
            ('scaler', StandardScaler())
        ])

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.coef_.tolist()
        return None

    def get_intercept(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.intercept_.tolist()
        return None

    def pretrain(self, X, y):
        X_scaled = self.pipeline.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.pretrained = True

    def train(self, X, y):
        if not self.is_fitted('pipeline'):
            self.pipeline.fit(X)
        weights = np.ones(len(y)) + self.times_trained * NEW_DATA_WEIGHT_DIFF
        X_scaled = self.pipeline.transform(X)
        self.model.partial_fit(X_scaled, y, sample_weight=weights)
        self.times_trained += 1

    def predict(self, X_dict):
        X_values = [[X_dict[var] for var in self.model_vars]]
        if not self.is_fitted('pipeline'):
            self.pipeline.fit(X_values)
        X_scaled = self.pipeline.transform(X_values)
        return self.model.predict(X_scaled)[0]     
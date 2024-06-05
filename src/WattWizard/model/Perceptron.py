from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from src.WattWizard.model.Model import Model


class Perceptron(Model):

    model = None
    scaler = None

    def __init__(self):
        super().__init__()
        self.model = MLPRegressor(hidden_layer_sizes=(), max_iter=10000, warm_start=False)
        self.scaler = StandardScaler()

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return [x for xs in self.model.coefs_[0].tolist() for x in xs]
        return None

    def get_intercept(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.intercepts_[0].tolist()
        return None

    def pretrain(self, X, y):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.pretrained = True

    def train(self, X, y):
        if not self.is_fitted('scaler'):
            self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)
        self.model.partial_fit(X_scaled, y)
        self.times_trained += 1

    def predict(self, X_dict):
        X_values = [[X_dict[var] for var in self.model_vars]]
        if not self.is_fitted('scaler'):
            self.scaler.fit(X_values)
        X_scaled = self.scaler.transform(X_values)
        return self.model.predict(X_scaled)[0]
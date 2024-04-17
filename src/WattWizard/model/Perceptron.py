from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from src.WattWizard.model.Model import Model


class Perceptron(Model):

    model = None
    scaler = None

    def __init__(self):
        super().__init__()
        self.model = MLPRegressor(hidden_layer_sizes=(100, 100), max_iter=2000, random_state=1,
                                      learning_rate_init=0.1, alpha=0.0001, solver='adam', n_iter_no_change=50, tol=1e-6)         
        self.scaler = StandardScaler()

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
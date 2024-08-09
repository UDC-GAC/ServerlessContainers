from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from src.WattWizard.model.Model import Model


class Perceptron(Model):

    model = None
    scaler = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.model = MLPRegressor(hidden_layer_sizes=(), max_iter=10000, warm_start=False)
        self.scaler = StandardScaler()
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": ['time_series', 'data_type'],
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return [x for xs in self.model.coefs_[0].tolist() for x in xs]
        return None

    def get_intercept(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.intercepts_[0].tolist()
        return None

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled, y_train)
        self.pretrained = True

    def train(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['train'], kwargs)
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        if not self.is_fitted('scaler'):
            self.scaler.fit(X_train)
        X_scaled = self.scaler.transform(X_train)
        self.model.partial_fit(X_scaled, y_train)
        self.times_trained += 1

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        X_test, y_test = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        if not self.is_fitted('scaler'):
            self.scaler.fit(X_test)
        X_scaled = self.scaler.transform(X_test)
        return self.model.predict(X_scaled)

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
        if not self.is_fitted('scaler'):
            self.scaler.fit(X_values)
        X_scaled = self.scaler.transform(X_values)
        return self.model.predict(X_scaled)[0]
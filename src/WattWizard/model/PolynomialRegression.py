from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model


class PolynomialRegression(Model):

    model = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.model = LinearRegression(fit_intercept=True)
        self.poly_features = PolynomialFeatures(degree=2, include_bias=True)
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": None,
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
        X_poly = self.poly_features.fit_transform(X_train)
        y_adjusted = y_train - self.idle_consumption
        self.model.fit(X_poly, y_adjusted)
        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_test, y_test = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        X_poly = self.poly_features.transform(X_test)
        return None, self.idle_consumption + self.model.predict(X_poly)

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
        X_poly = self.poly_features.transform(X_values)
        return self.idle_consumption + self.model.predict(X_poly)[0]

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model


class PolynomialRegression(Model):

    model = None

    def __init__(self):
        super().__init__()
        self.model = LinearRegression(fit_intercept=False)
        self.poly_features = PolynomialFeatures(degree=2, include_bias=False)

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.coef_.tolist()
        return None

    def get_intercept(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.intercept_
        return None

    def pretrain(self, X, y):
        X_poly = self.poly_features.fit_transform(X)
        self.model.fit(X_poly, y)
        self.pretrained = True

    def train(self):
        raise TypeError("This method doesn't support online learning")

    def predict(self, X_dict):
        X_values = [[X_dict[var] for var in self.model_vars]]
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_poly = self.poly_features.transform(X_values)
        return self.idle_consumption + self.model.predict(X_poly)[0]

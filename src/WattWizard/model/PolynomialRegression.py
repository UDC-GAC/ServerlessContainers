from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model

class PolynomialRegression(Model):

    model = None

    def __init__(self):
        super().__init__()
        self.model = LinearRegression()
        self.poly_features = PolynomialFeatures(degree=2)

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
        return self.model.predict(X_poly)[0]

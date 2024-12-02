from sklearn.ensemble import RandomForestRegressor

from src.WattWizard.model.Model import Model


class RandomForest(Model):

    model = None

    # TODO: Fine-tune other RandomForest parameters
    # MAPE values for different min_samples_split
    # ============================================
    # min_samples_split |   BT_IO   |     IS    |     FT    |     BT    |     CG    |     MG    | dummy_test |
    # ------------------|-----------|-----------|-----------|-----------|-----------|-----------|------------|
    #         2         |   0.1000  |   0.1000  |   0.0730  |   0.0721  |   0.0598  |   0.0784  |   0.1223   |
    #        10         |   0.0966  |   0.1034  |   0.0703  |   0.0658  |   0.0585  |   0.0776  |   0.1243   |
    #        20         |   0.0947  |   0.1102  |   0.0679  |   0.0617  |   0.0582  |   0.0755  |   0.1257   |
    #        30         |   0.0933  |   0.1151  |   0.0645  |   0.0585  |   0.0575  |   0.0730  |   0.1272   |
    #        40         |   0.0897  |   0.1160  |   0.0646  |   0.0553  |   0.0561  |   0.0733  |   0.1266   |
    #        50         |   0.0889  |   0.1175  |   0.0650  |   0.0541  |   0.0559  |   0.0731  |   0.1271   |
    #       100         |   0.0869  |   0.1256  |   0.0626  |   0.0528  |   0.0558  |   0.0709  |   0.1281   |
    # ============================================

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.model = RandomForestRegressor(n_estimators=100, random_state=42, min_samples_split=50)
        self.required_kwargs_map.update({
            "pretrain": ['time_series', 'data_type'],
            "train": None,
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })

    def get_coefs(self):
        if self.pretrained or self.times_trained > 0:
            return self.model.feature_importances_.tolist()
        return None

    def get_intercept(self):
        return self.idle_consumption

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)
        X_train, y_train = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        self.model.fit(X_train, y_train)
        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_test, y_test = self.get_model_data(kwargs['time_series'], kwargs['data_type'])
        return None, self.model.predict(X_test)

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
        return self.model.predict(X_values)[0]


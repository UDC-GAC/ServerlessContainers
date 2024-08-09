import numpy as np

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model


class MultiSocketRegresion(Model):

    model = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.check_required_kwargs(['sockets', 'cores_distribution'], kwargs)
        if kwargs['sockets'] > 2:
            raise NotImplementedError("Multisocket models with more than two sockets are not yet supported")
        self.sockets = kwargs['sockets']
        self.cores_distribution = kwargs['cores_distribution']
        self.models = {}
        self.poly_features = {}
        self.idle_consumption = {}
        self.required_kwargs_map.update({
            "df_to_model_data": ['cpu_number'],
            "pretrain": ['time_series', 'data_type'],
            "train": None,
            "test": ['time_series', 'data_type'],
            "predict": ['X_dict']
        })
        for i in range(self.sockets):
            self.models[f"CPU{i}_active"] = LinearRegression(fit_intercept=False)
            self.models[f"CPU{i}_running"] = LinearRegression(fit_intercept=False)

            self.poly_features[f"CPU{i}_active"] = PolynomialFeatures(degree=2, include_bias=False)
            self.poly_features[f"CPU{i}_running"] = PolynomialFeatures(degree=2, include_bias=False)

    def get_coefs(self):
        pass

    def get_intercept(self):
        pass

    def get_idle_consumption(self):
        total = 0
        for i in range(self.sockets):
            total += self.idle_consumption[f"CPU{i}"]
        return total

    def set_idle_consumption(self, time_series):
        if "power" not in time_series:
            raise TypeError("Missing power in idle time series while setting idle consumption")
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            cpu_mask = time_series["exp_name"].str.startswith(current_cpu)
            self.idle_consumption[current_cpu] = time_series.loc[cpu_mask, f"power_pkg{i}"].mean()

    def df_to_model_data(self, df, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['df_to_model_data'], kwargs)
        power_var = f"power_pkg{kwargs['cpu_number']}" if kwargs['cpu_number'] >= 0 else "power"
        x_values = []
        for var in self.model_vars:
            if var in df:
                x_values.append(df[var].values.reshape(-1, 1))
            else:
                raise TypeError(f"Missing variable {var} in DataFrame")
        x_stack = np.hstack(x_values)
        if power_var in df:
            y = df[power_var].values
        else:
            raise TypeError(f"Missing {power_var} data in DataFrame")
        return x_stack, y

    def pretrain(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['pretrain'], kwargs)

        cpu_time_series = {}
        # Train running models where (power when CPU is being used)
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            cpu_mask = kwargs['time_series']["exp_name"].str.startswith(current_cpu)
            cpu_time_series[current_cpu] = kwargs['time_series'].loc[cpu_mask, :]
            X_train, y_train = self.df_to_model_data(cpu_time_series[current_cpu], cpu_number=i)
            X_poly = self.poly_features[current_cpu].fit_transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"CPU{i}_running"].fit(X_poly, y_adjusted)

        # Train active models (power when other CPU is being used)
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            next_cpu = f"CPU{(i+1) % self.sockets}"
            X_train, y_train = self.df_to_model_data(cpu_time_series[next_cpu], cpu_number=i)
            X_poly = self.poly_features[current_cpu].transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"CPU{i}_active"].fit(X_poly, y_adjusted)

        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    # TODO: Implement bulk prediction based on used cores
    #  (maybe used_cores could be inserted in time series in this case)
    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
    #     if not self.pretrained:
    #         raise TypeError("Model not fitted yet, first train the model, then predict")
    #     X_test, y_test = self.df_to_model_data(kwargs['time_series'], cpu_number=-1)
    #     X_poly = self.poly_features.transform(X_test)
    #     return self.model.predict(X_poly) + self.idle_consumption
    #

    # TODO: Implement prediction based on used cores (passed as an argument)
    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
    #     X_values = [[kwargs['X_dict'][var] for var in self.model_vars]]
    #     if not self.pretrained:
    #         raise TypeError("Model not fitted yet, first train the model, then predict")
    #     X_poly = self.poly_features.transform(X_values)
    #     return self.idle_consumption + self.model.predict(X_poly)[0]

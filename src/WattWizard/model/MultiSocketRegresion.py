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
        self.total_idle_consumption = 0
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
        return self.total_idle_consumption

    def set_idle_consumption(self, time_series):
        if "power" not in time_series:
            raise TypeError("Missing power in idle time series while setting idle consumption")
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            cpu_mask = time_series["exp_name"].str.startswith(current_cpu)
            self.idle_consumption[current_cpu] = time_series.loc[cpu_mask, f"power_pkg{i}"].mean()
            self.total_idle_consumption += self.idle_consumption[current_cpu]

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
        # Train running models - power consumption of a CPU socket whent it is being used
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            cpu_mask = kwargs['time_series']["exp_name"].str.startswith(current_cpu)
            cpu_time_series[current_cpu] = kwargs['time_series'].loc[cpu_mask, :]
            X_train, y_train = self.df_to_model_data(cpu_time_series[current_cpu], cpu_number=i)
            X_poly = self.poly_features[current_cpu].fit_transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"CPU{i}_running"].fit(X_poly, y_adjusted)

        # Train active models - power consumption of a CPU socket when it is idle and other socket is being used
        # In this case we train each socket model when socket + 1 is being used
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            next_cpu = f"CPU{(i+1) % self.sockets}"
            # We use time series of next cpu together with the power of this CPU, that is, the power
            # consumption of current CPU while other CPU is being used
            X_train, y_train = self.df_to_model_data(cpu_time_series[next_cpu], cpu_number=i)
            X_poly = self.poly_features[current_cpu].transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"CPU{i}_active"].fit(X_poly, y_adjusted)

        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")

        return kwargs['time_series'].apply(lambda row: self.predict(X_dict=row), axis=1)

    def _get_cpu_from_core(self, core):
        for cpu, cores in self.cores_distribution.items():
            if core in cores:
                return cpu
        raise ValueError(f"Core {core} not found in cores distribution")

    # TODO: Take into account one CPU could be used much more than other CPU
    # For instance, CPU0 used at 80% and CPU1 at 10% is not the same as both at 45%
    def _get_socket_usages(self, X_dict):

        # Initialise cpu_usages
        cpu_usages = {}
        for i in range(0, self.sockets):
            cpu_usages[f'CPU{i}'] = {'used': 0}

        # Check which cores are being used
        cpus_count = 0
        cores = X_dict['cores']
        for core in cores:
            cpu = self._get_cpu_from_core(core)
            if cpu_usages[cpu]['used'] == 0:
                cpu_usages[cpu]['used'] = 1
                cpus_count += 1

        # Spread the resources usage among CPUs considering they all use a proportional amount of resources
        # In the future we should have info in time series of how much usage belongs to each core to have the real proportions
        for var in self.model_vars:
            for i in range(0, self.sockets):
                if cpu_usages[f'CPU{i}']['used'] == 1:
                    cpu_usages[f'CPU{i}'][var] = X_dict[var] / cpus_count

        return cpu_usages

    def _predict_running(self, cpu, cpu_usages):
        X_values = [[cpu_usages[cpu][var] for var in self.model_vars]]
        X_poly = self.poly_features[cpu].transform(X_values)
        return self.models[f"{cpu}_running"].predict(X_poly)[0]

    def _predict_active(self, cpu, cpu_usages):
        # Get next CPU number as we did in training
        next_cpu = f"CPU{(int(cpu[:-1]) + 1) % self.sockets}"
        X_values = [[cpu_usages[next_cpu][var] for var in self.model_vars]]
        X_poly = self.poly_features[cpu].transform(X_values)
        return self.models[f"{cpu}_active"].predict(X_poly)[0]

    # TODO: Pass as argument the cores used together with their usage disaggregated by core
    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")
        cpu_usages = self._get_socket_usages(kwargs['X_dict'])

        total_power = 0
        for cpu in cpu_usages:
            if cpu_usages[cpu]['used'] == 1:
                # Running: Power consumption of the socket while it is being used
                cpu_usages[cpu]['predicted_power'] = self._predict_running(cpu, cpu_usages)
            else:
                # Active: Power consumption of the socket while it is not being used but other sockets are
                cpu_usages[cpu]['predicted_power'] = self._predict_active(cpu, cpu_usages)
            total_power += cpu_usages[cpu]['predicted_power']

        return self.total_idle_consumption + total_power

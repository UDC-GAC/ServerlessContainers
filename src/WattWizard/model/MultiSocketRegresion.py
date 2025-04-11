import numpy as np

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

from src.WattWizard.model.Model import Model

MAX_ERROR = 0.001
MAX_ITERS = 100


class MultiSocketRegresion(Model):
    model = None

    def __init__(self, **kwargs):
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
            "predict": ['X_dict', 'core_usages'],
            "get_inverse_prediction": ["X_dict", "core_usages", "host_cores_mapping"],
            "get_adjusted_inverse_prediction": ["X_dict", "core_usages", "host_cores_mapping"]
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
            self.idle_consumption[current_cpu] = time_series.loc[:, f"power_pkg{i}"].mean()
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
            X_poly = self.poly_features[f"{current_cpu}_running"].fit_transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"{current_cpu}_running"].fit(X_poly, y_adjusted)

        # Train active models - power consumption of a CPU socket when it is idle and other socket is being used
        # In this case we train each socket model when socket + 1 is being used
        for i in range(self.sockets):
            current_cpu = f"CPU{i}"
            next_cpu = f"CPU{(i + 1) % self.sockets}"
            # We use time series of next cpu together with the power of this CPU, that is, the power
            # consumption of current CPU while other CPU is being used
            X_train, y_train = self.df_to_model_data(cpu_time_series[next_cpu], cpu_number=i)
            X_poly = self.poly_features[f"{current_cpu}_active"].fit_transform(X_train)
            y_adjusted = y_train - self.idle_consumption[current_cpu]
            self.models[f"{current_cpu}_active"].fit(X_poly, y_adjusted)

        self.pretrained = True

    def train(self, *args, **kwargs):
        raise TypeError("This method doesn't support online learning")

    def test(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['test'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")

        time_series = kwargs['time_series']
        time_series['cores'] = time_series['cores'].astype(str)
        core_usages = time_series['cores'].apply(lambda c: c.split(',')).values

        @np.vectorize
        def _np_predict(X_dict, cores):
            return self.predict(X_dict=X_dict, core_usages=cores)

        return None, _np_predict(time_series[self.model_vars].to_dict(orient='records'), core_usages)

    def _create_core_usages(self, X_dict, cores):
        """Create a dictionary of cores by distributing the usage level of each variable sequentially among the
        available cores.

        Args:
            X_dict (dict): Dictionary containing the total usage of each variable in the model.
            cores (list): List of cores being used.

        Returns:
            (dict) Dictionary containing the usage of each variable in the model per core.

        """
        total_var_amount = X_dict.copy()
        core_usages = {}
        for core in cores:
            core_usages[core] = {}
            for var in self.model_vars:
                if total_var_amount[var] > 100:
                    core_usages[core][var] = 100
                    total_var_amount[var] -= 100
                else:
                    core_usages[core][var] = total_var_amount[var]
                    total_var_amount[var] = 0
        return core_usages

    def _get_cpu_from_core(self, core):
        for cpu, cores in self.cores_distribution.items():
            if core in cores:
                return cpu
        raise ValueError(f"Core {core} not found in cores distribution")

    def _get_socket_usages(self, core_usages):
        """Aggregates the usage of each variable at the socket level, from the disaggregated usage by core.

        Args:
            core_usages (dict): Dictionary containing the usage of each variable in the model per core.

        Returns:
            (dict) Dictionary containing the usage of each variable in the model per socket.

        """
        # Initialise cpu_usages
        cpu_usages = {}
        for i in range(0, self.sockets):
            cpu_usages[f'CPU{i}'] = {"used": False}
            for var in self.model_vars:
                cpu_usages[f'CPU{i}'][var] = 0

        # Check which cores are being used in each cpu
        for core in core_usages:
            cpu = self._get_cpu_from_core(core)
            cpu_usages[cpu]["used"] = True
            for var in self.model_vars:
                cpu_usages[cpu][var] += core_usages[core][var]

        return cpu_usages

    def _predict_running(self, cpu, cpu_usages):
        X_values = [[cpu_usages[cpu][var] for var in self.model_vars]]
        X_poly = self.poly_features[f"{cpu}_running"].transform(X_values)
        return self.models[f"{cpu}_running"].predict(X_poly)[0]

    def _predict_active(self, cpu, next_cpu, cpu_usages):
        X_values = [[cpu_usages[next_cpu][var] for var in self.model_vars]]
        X_poly = self.poly_features[f"{cpu}_active"].transform(X_values)
        return self.models[f"{cpu}_active"].predict(X_poly)[0]

    def predict(self, *args, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['predict'], kwargs)
        if not self.pretrained:
            raise TypeError("Model not fitted yet, first train the model, then predict")

        # If just a list of cores is passed the usage of each resource is sequentally distributed among cores
        if isinstance(kwargs['core_usages'], list):
            kwargs['core_usages'] = self._create_core_usages(kwargs['X_dict'], kwargs['core_usages'])

        # Aggregate usage per socket
        cpu_usages = self._get_socket_usages(kwargs['core_usages'])
        total_power = 0
        for cpu in cpu_usages:
            if cpu_usages[cpu]['used']:
                # Running: Power consumption of the socket while it is being used
                cpu_usages[cpu]['predicted_power'] = self._predict_running(cpu, cpu_usages)
            else:
                # Active: Power consumption of the socket while it is not being used but other sockets are
                next_cpu = f"CPU{(int(cpu[-1:]) + 1) % self.sockets}"  # Get next CPU number as we did in training
                if cpu_usages[next_cpu]['used']:
                    cpu_usages[cpu]['predicted_power'] = self._predict_active(cpu, next_cpu, cpu_usages)
                else:
                    cpu_usages[cpu]['predicted_power'] = 0
            total_power += cpu_usages[cpu]['predicted_power']

        return self.total_idle_consumption + total_power

    @staticmethod
    def get_total_value(dynamic_var, core_usages):
        total_value = 0
        for core_usage in core_usages.values():
            total_value += core_usage[dynamic_var]
        return total_value

    def _rescale_cores(self, dynamic_var, core_usages, host_cores_mapping, amount):
        """It rescales the usage of each core in a similar way to Scaler.

        Args:
            dynamic_var (str): Model variable to rescale. Currently only user_load rescaling is supported.
            core_usages (dict): Dictionary containing the usage of each variable in the model per core.
            host_cores_mapping (dict): Dictionary containing the free CPU of each core in the host.
            amount (int): Amount of CPU usage (shares) to rescale.

        Returns:
            (dict) Dictionary containing the updated values of usage per core after rescaling.
        """

        # Rescale up
        if amount > 0:
            needed_shares = amount

            # First fill the already used cores so that no additional cores are added unnecessarily
            for core in core_usages:
                free_shares = 100 - core_usages[core]['system_load'] - core_usages[core][dynamic_var]
                if free_shares > needed_shares:
                    core_usages[core][dynamic_var] += needed_shares
                    needed_shares = 0
                    break
                else:
                    core_usages[core][dynamic_var] += free_shares
                    needed_shares -= free_shares

            # If we need more cores we add as many cores as necessary, starting with the ones with the largest
            # free shares to avoid too much spread
            if needed_shares > 0:
                less_used_cores = list()
                for core in host_cores_mapping:
                    if core not in core_usages:
                        less_used_cores.append((core, host_cores_mapping[core]["free"]))
                less_used_cores.sort(key=lambda tup: tup[1], reverse=True)

                for core, free_shares in less_used_cores:
                    core_usages[core] = {}
                    if free_shares > 0 and needed_shares > 0:
                        for var in self.model_vars:
                            core_usages[core][var] = 0
                        if free_shares >= needed_shares:
                            core_usages[core][dynamic_var] += needed_shares
                            needed_shares = 0
                            break
                        else:
                            core_usages[core][dynamic_var] += free_shares
                            needed_shares -= free_shares

            if needed_shares > 0:
                raise ValueError(f"Error rescaling {dynamic_var} up, missing {needed_shares} shares")

        elif amount < 0:
            shares_to_free = abs(amount)
            l = [(core, core_usages[core][dynamic_var]) for core in core_usages]
            l.sort(key=lambda tup: tup[1], reverse=False)
            less_used_cores = [i[0] for i in l]
            for core in less_used_cores:
                if core_usages[core][dynamic_var] >= shares_to_free:
                    core_usages[core][dynamic_var] -= shares_to_free
                    shares_to_free = 0
                else:
                    shares_to_free -= core_usages[core][dynamic_var]
                    core_usages[core][dynamic_var] = 0

                if shares_to_free == 0:
                    break
                    
            if shares_to_free > 0:
                raise ValueError(f"Error rescaling {dynamic_var} down, {shares_to_free} shares pending to free")
            
        return core_usages

    def get_inverse_prediction(self, desired_power, dynamic_var, limits, **kwargs):
        self.check_required_kwargs(self.required_kwargs_map['get_inverse_prediction'], kwargs)
        count_iters = 0
        # Get total usage of dynamic_var (tipically user_load)
        dynamic_var_value = self.get_total_value(dynamic_var, kwargs['core_usages'])
        estimated_power = self.predict(**kwargs)
        error = abs(desired_power - estimated_power)
        while error > MAX_ERROR and count_iters < MAX_ITERS and limits["min"] < dynamic_var_value < limits["max"]:
            # Get new dynamic_var value based on estimation error
            new_dynamic_var_value = desired_power * dynamic_var_value / estimated_power

            # Rescale cores according to new dynamic_var value
            kwargs['core_usages'] = self._rescale_cores(dynamic_var, kwargs['core_usages'], kwargs['host_cores_mapping'],
                                                       new_dynamic_var_value - dynamic_var_value)

            # Get new prediction with new cores
            estimated_power = self.predict(**kwargs)

            # Check error and update dynamic_var value
            error = abs(desired_power - estimated_power)
            dynamic_var_value = new_dynamic_var_value
            count_iters += 1

        return {
            "value": max(limits["min"], min(limits["max"], dynamic_var_value))
        }

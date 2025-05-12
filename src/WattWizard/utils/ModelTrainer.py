import os
from src.WattWizard.logs.logger import log


class ModelTrainer:

    def __init__(self, config, ts_plotter, data_loader):
        self.config = config
        self.timestamps_dir = self.config.get_argument("train_timestamps_dir")
        self.join_timestamps = self.config.get_argument("join_train_timestamps")
        self.ts_plotter = ts_plotter
        self.data_loader = data_loader

    def _plot_train_data(self, model, structure, ts_data):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "train")
        self.ts_plotter.set_output_dir(output_dir)
        log(f"Plotting train data for model {model['name']}. Plots will be stored at {output_dir}")

        # If model is HW aware generate separated plots for each socket
        # Also separate running data and active data (idle while the other socket is running)
        if model.get('hw_aware', False):
            sockets = self.config.get_argument("sockets")
            for i in range(sockets):
                current_cpu = f"CPU{i}"
                next_cpu = f"CPU{(i + 1) % sockets}"
                cpu_mask = ts_data["exp_name"].str.startswith(current_cpu)
                cpu_ts = ts_data.loc[cpu_mask, :]
                self.ts_plotter.plot_time_series(f"{model['name']}_{current_cpu}_running_data", cpu_ts,
                                                 self.config.get_argument("model_variables"), power_var=f"power_pkg{i}")
                self.ts_plotter.plot_time_series(f"{model['name']}_{next_cpu}_active_data", cpu_ts,
                                                 self.config.get_argument("model_variables"), power_var=f"power_pkg{(i+1) % sockets}")
        else:
            self.ts_plotter.plot_time_series(f"{model['name']}_train_data", ts_data, self.config.get_argument("model_variables"))

        # Generate plots comparing power with each model variable
        self.ts_plotter.plot_vars_vs_power(ts_data, self.config.get_argument("model_variables"))

    def pretrain_model(self, structure, model):
        # Load train data (idle + running)
        idle_data = self.data_loader.load_time_series(structure, self.timestamps_dir, model['train_file_name'], idle=True)
        ts_data = self.data_loader.load_time_series(structure, self.timestamps_dir, model['train_file_name'], idle=False, join=self.join_timestamps)
        try:
            # Set idle consumption and train model
            model['instance'].set_idle_consumption(idle_data)
            model['instance'].pretrain(time_series=ts_data, data_type="df")
            log(f"Model {model['name']} successfully pretrained")

            # Plot train time series if specified
            if self.config.get_argument("plot_time_series"):
                self._plot_train_data(model, structure, ts_data)
        except Exception as e:
            log(f"Error while training model {model['name']}: {str(e)}", "ERR")

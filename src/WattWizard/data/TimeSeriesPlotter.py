import seaborn as sns
import matplotlib.pyplot as plt
import os
from matplotlib.lines import Line2D

DEFAULT_LABELS = {
    "load": "Utilization (%)",
    "user_load": "User Utilization (%)",
    "system_load": "System Utilization (%)",
    "p_user_load": "Physical User Usage (%)",
    "p_system_load": "Physical System Usage (%)",
    "l_user_load": "Logical User Usage (%)",
    "l_system_load": "Logical System Usage (%)",
    "wait_load": "IO Wait Utilization (%)",
    "freq": "Avg Frequency (MHz)",
    "sumfreq": "Sum Frequency (MHz)",
    "temp": "Temperature Cº",
    "power": "Power Consumption (W)",
    "power_pkg0": "Power Consumption CPU0 (W)",
    "power_pkg1": "Power Consumption CPU1 (W)",
    "power_predicted": "Predicted Power Consumption (W)"
}

DEFAULT_COLORS = {
    "load": "#2b83ba",
    "user_load": "#2b83ba",
    "system_load": "#5e3c99",
    "p_user_load": "#2b83ba",
    "p_system_load": "#5e3c99",
    "l_user_load": "#f781bf",
    "l_system_load": "#d7191c",
    "wait_load": "#f781bf",
    "freq": "#d7191c",
    "sumfreq": "#d7191c",
    "temp": "#f781bf",
    "power": "#fdae61",
    "power_pkg0": "#fdae61",
    "power_pkg1": "#fdae61",
    "power_predicted": "#008837"
}

DEFAULT_MARKERS = {
    "load": "o",
    "user_load": "o",
    "system_load": "s",
    "p_user_load": "o",
    "p_system_load": "s",
    "l_user_load": "d",
    "l_system_load": "X",
    "wait_load": "d",
    "freq": "X",
    "sumfreq": "X",
    "temp": None,
    "power": None,
    "power_pkg0": None,
    "power_pkg1": None,
    "power_predicted": None
}


# TODO: Implement class to plot train time series
class TimeSeriesPlotter:

    output_dir = None

    def __init__(self, output_dir=None):
        plt.switch_backend('agg')
        self.output_dir = output_dir
        if output_dir:
            self.create_non_existent_dir(output_dir)

    def set_output_dir(self, output_dir):
        self.output_dir = output_dir
        self.create_non_existent_dir(output_dir)

    def save_plot(self, name):
        path = f'{self.output_dir}/{name}.png'
        plt.tight_layout()
        plt.savefig(path, bbox_inches='tight')

    @staticmethod
    def create_non_existent_dir(dir):
        if not os.path.exists(dir):
            os.makedirs(dir)

    @staticmethod
    def get_key_from_default_value(dict, value):
        for k, v in dict.items():
            if v == value:
                return k

    @staticmethod
    def set_legend_with_markers(ax1, ax2):
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()

        custom_lines = []
        for line, label in zip(lines1 + lines2, labels1 + labels2):
            if isinstance(line, Line2D):
                var = TimeSeriesPlotter.get_key_from_default_value(DEFAULT_LABELS, label)
                custom_line = Line2D([0], [0], color=line.get_color(), markerfacecolor="black",
                                     marker=DEFAULT_MARKERS[var], markersize=10, label=label,
                                     linestyle=line.get_linestyle())
                custom_lines.append(custom_line)
        ax1.legend(handles=custom_lines, loc="center left", bbox_to_anchor=(0, 1.5))
        ax2.get_legend().remove()

    @staticmethod
    def set_basic_labels(title, xlabel, ylabel, ax):
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    @staticmethod
    def set_line_plot(var, df, ax):
        x = df["time_diff"]
        y = df[var]
        linestyle = "dashed" if var == "power_predicted" else "solid"
        color = DEFAULT_COLORS[var]
        label = DEFAULT_LABELS[var]
        marker = DEFAULT_MARKERS[var]
        sns.lineplot(x=x, y=y, ax=ax, color=color, label=label, linestyle=linestyle)
        if marker is not None:
            ax.scatter(x[::50], y[::50], s=20, color="black", marker=marker, zorder=3, edgecolors=color, linewidths=0.2)

    def plot_time_series(self, filename, time_series, model_variables, power_var="power"):
        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax2 = ax1.twinx()

        # Plot 1 line for each predictor variable (Left Axis: ax1)
        for var in model_variables:
            self.set_line_plot(var, time_series, ax1)

        # Plot dependent variable "power" (Right Axis: ax2)
        self.set_line_plot(power_var, time_series, ax2)

        self.set_basic_labels(None, f"Time ({time_series['time_unit'].iloc[0]})", "CPU Model Variables", ax1)
        self.set_basic_labels(None, None, "Power Consumption (W)", ax2)
        self.set_legend_with_markers(ax1, ax2)
        self.save_plot(filename)

        plt.close(fig)

    def plot_test_time_series(self, test_app_name, time_series, model_variables):
        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax2 = ax1.twinx()

        # Plot 1 line for each predictor variable (Left Axis: ax1)
        for var in model_variables:
            self.set_line_plot(var, time_series, ax1)

        # Plot dependent variables "power" and "predicted_power" (Right Axis: ax2)
        self.set_line_plot("power", time_series, ax2)
        self.set_line_plot("power_predicted", time_series, ax2)

        self.set_basic_labels(None, f"Time ({time_series['time_unit'].iloc[0]})", "CPU Model Variables", ax1)
        self.set_basic_labels(None, None, "Power Consumption (W)", ax2)
        self.set_legend_with_markers(ax1, ax2)
        self.save_plot(test_app_name)

        plt.close(fig)

    def plot_vars_vs_power(self, time_series, model_variables):
        for var in model_variables:
            fig, ax = plt.subplots(figsize=(14, 6))
            sns.scatterplot(x=time_series[var], y=time_series["power"], color="#fdae61")
            self.set_basic_labels(f"{var} VS power", DEFAULT_LABELS[var], DEFAULT_LABELS["power"], ax)
            ax.set_title(f"{var} VS power")
            self.save_plot(f"{var}_vs_power")
            plt.close(fig)

import os
from src.WattWizard.logs.logger import log
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error, r2_score, max_error, mean_absolute_error


class ModelTester:

    def __init__(self, config, ts_plotter, data_loader):
        self.config = config
        self.timestamps_dir = self.config.get_argument("test_timestamps_dir")
        self.join_timestamps = self.config.get_argument("join_test_timestamps")
        self.ts_plotter = ts_plotter
        self.data_loader = data_loader
        # Formatting variables
        self.line_width = 80
        self.white_spaces_name = 3
        self.number_of_decimals = 4

    def _get_header(self, test_name):
        return (("*" * self.line_width) + "\n" +
                (" " * self.white_spaces_name + test_name + " " * self.white_spaces_name).center(self.line_width, "*")
                + "\n")

    def _get_metric_line(self, test_name, metric_name, metric_value):
        return "[" + test_name + "] " + f"{metric_name + ':':<12}" + f"{metric_value:.{self.number_of_decimals}f}" + "\n"

    def _write_results(self, structure, model, test_data, test_name):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        results_file = os.path.join(output_dir, "results")
        expected = test_data['power']
        predicted = test_data['power_predicted']

        # Get accuracy metrics over the test data
        metrics = {
            "MAPE": mean_absolute_percentage_error(expected, predicted),
            "MSE": mean_squared_error(expected, predicted),
            "R2": r2_score(expected, predicted),
            "MAE": mean_absolute_error(expected, predicted),
            "MAX ERROR": max_error(expected, predicted)
        }

        # Write results
        with open(results_file, "a") as f:
            f.write(self._get_header(test_name))
            for metric_name, metric_value in metrics.items():
                f.write(self._get_metric_line(test_name, metric_name, metric_value))

    def _plot_test_data(self, structure, model, test_data, test_name):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        self.ts_plotter.set_output_dir(output_dir)
        log(f"Plotting test data for model {model['name']}. Plots will be stored at {output_dir}")
        self.ts_plotter.plot_test_time_series(f"{model['name']}_{test_name}", test_data, self.config.get_argument("model_variables"))

    def test_model(self, structure, model, test_file):
        test_name = os.path.splitext(os.path.basename(test_file))[0]
        log(f"Evaluating model {model['name']} with test {test_name}")
        test_data = self.data_loader.load_time_series(structure, self.timestamps_dir, test_name, idle=False, join=self.join_timestamps)

        # Get model predictions for test dataset
        new_data, power_pred = model['instance'].test(time_series=test_data, data_type="df")

        # If the model make changes over the test dataset, update the dataset to plot
        if new_data is not None:
            test_data = new_data

        # Add predictions columns
        test_data["power_predicted"] = power_pred.flatten()

        # Write accuracy results
        self._write_results(structure, model, test_data, test_name)

        # Plot test time series if specified
        if self.config.get_argument("plot_time_series"):
            self._plot_test_data(structure, model, test_data, test_name)

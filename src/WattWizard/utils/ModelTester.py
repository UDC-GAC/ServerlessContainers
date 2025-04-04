import os
import shutil
from src.WattWizard.logs.logger import log
from sklearn.metrics import mean_absolute_percentage_error


class ModelTester:
    def __init__(self, config, ts_plotter, data_loader):
        self.config = config
        self.timestamps_dir = self.config.get_argument("test_timestamps_dir")
        self.ts_plotter = ts_plotter
        self.data_loader = data_loader

    # def test_models(self, models):
    #     for test_file in self.config.get_argument("test_files"):
    #         # Extraer el nombre base (sin extensión) del archivo de test
    #         filename = os.path.splitext(os.path.basename(test_file))[0]
    #         log(f"Processing test file: {test_file} (base name: {filename})")
    #         # Cargar los datos de test reutilizando DataLoader (aprovecha CSV si existe)
    #         # Para test no es necesario pasar una estructura específica, se pasa cadena vacía
    #         test_data = self.data_loader.load_time_series(self.test_dir, filename, "", idle=False)
    #         test_name = filename
    #         for model in models:
    #             output_dir = os.path.join(
    #                 self.config.get_argument("plot_time_series_dir"),
    #                 model['structure'], model['name'], "test"
    #             )
    #             # Ejecutar el método de test del modelo con una copia de los datos de test
    #             new_ts, power_pred = model['instance'].test(time_series=test_data.copy(), data_type="df")
    #             if new_ts is not None:
    #                 test_data = new_ts
    #             test_data['power_predicted'] = power_pred.flatten()
    #             self._write_results(test_data['power'], test_data['power_predicted'], output_dir, test_name)
    #             if self.config.get_argument("plot_time_series"):
    #                 self.ts_plotter.set_output_dir(output_dir)
    #                 self.ts_plotter.plot_test_time_series(
    #                     f"{model['name']}_{test_name}",
    #                     f"Test for model {model['name']} - {test_name}",
    #                     test_data,
    #                     self.config.get_argument("model_variables")
    #                 )

    def _clean_model_test_dir(self, structure, model):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    def _write_results(self, structure, model, test_data, test_name):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        results_file = os.path.join(output_dir, "results")
        expected = test_data['power']
        predicted = test_data['power_predicted']

        # Get accuracy metrics over the test data
        mape = mean_absolute_percentage_error(expected, predicted)

        # Write results
        with open(results_file, "a") as f:
            f.write(f"************************************************************************\n")
            f.write(f"[{test_name}] MAPE: {mape}\n")
            f.write(f"************************************************************************\n")

    def _plot_test_data(self, structure, model, test_data, test_name):
        output_dir = os.path.join(self.config.get_argument("plot_time_series_dir"), structure, model['name'], "test")
        self.ts_plotter.set_output_dir(output_dir)
        self.ts_plotter.plot_test_time_series(f"{model['name']}_{test_name}", test_data, self.config.get_argument("model_variables"))

    def test_model(self, structure, model, test_file):
        self._clean_model_test_dir(structure, model)
        test_name = os.path.splitext(os.path.basename(test_file))[0]
        log(f"Evaluating model {model['name']} with test {test_name}")
        test_data = self.data_loader.load_time_series(structure, self.timestamps_dir, test_name, idle=False)

        # Get model predictions for test dataset
        new_data, power_pred = model['instance'].test(time_series=test_data, data_type="df")

        # If the model make changes over the test dataset, update the dataset to plot
        if new_data:
            test_data = new_data

        # Add predictions columns
        test_data["power_predicted"] = power_pred.flatten()

        # Write accuracy results
        self._write_results(structure, model, test_data, test_name)

        # Plot test time series if specified
        if self.config.get_argument("plot_time_series"):
            self._plot_test_data(structure, model, test_data, test_name)

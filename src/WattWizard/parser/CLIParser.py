import argparse
from argparse import RawTextHelpFormatter


class CLIParser:

    def __init__(self):
        self.args_dict = None
        self.parser = argparse.ArgumentParser(
            description="CPU Power Modeling from Time Series.",
            formatter_class=RawTextHelpFormatter
        )

        self.parser.add_argument(
            "-v",
            "--verbose",
            action="store_const",
            const=True,
            help="Increase output verbosity",
        )

        self.parser.add_argument(
            "-i",
            "--influxdb-host",
            help="If pretrain data is specified you must indicate an InfluxDB Host to retrieve data from.",
        )

        self.parser.add_argument(
            "-b",
            "--influxdb-bucket",
            help="If pretrain data is specified you must indicate an InfluxDB Bucket to retrieve data from.",
        )

        self.parser.add_argument(
            "--influxdb-token",
            help="If pretrain data is specified you must indicate an InfluxDB Token to retrieve data from.",
        )

        self.parser.add_argument(
            "--influxdb-org",
            help="If pretrain data is specified you must indicate an InfluxDB Organization to retrieve data from.",
        )

        self.parser.add_argument(
            "-p",
            "--prediction-methods",
            help="Comma-separated list of methods used to predict CPU power consumption. By default is a SGD Regressor. Supported methods:\n\
    \tmlpregressor\t\t\tMultilayer Perceptron Regressor\n\
    \tsgdregressor\t\t\tPolynomial Regression fitted by SGD\n\
    \tpolyreg\t\t\t\tPolynomial Regression (Doesn't have support for online learning)",
        )

        self.parser.add_argument(
            "-m",
            "--model-variables",
            help="Comma-separated list of variables to use in the model. Commonly known as features. \
    \nSupported values: user_load, system_load, wait_load, freq, sumfreq.",
        )

        self.parser.add_argument(
            "--timestamps-dir",
            help="Directory in which the timestamp files to train models are stored. By default is ./conf/WattWizard/timestamps.",
        )

        self.parser.add_argument(
            "--train-files",
            help="Comma-separated list of train file names stored under timestamps directory (or 'all' keyword to use all files in this directory). \n\
One model per train file and prediction method will be created if possible. Each file must store time series timestamps from pretrain \n\
data in proper format. Check README.md to see timestamps proper format.",
        )

        self.parser.add_argument(
            "--plot-time-series",
            action="store_const",
            const=False,
            help="Plot the time series used to train each model",
        )

        self.parser.add_argument(
            "--plot-time-series-dir",
            help="Directory to store a plot of the train time series for each model. Works together with option --plot-time-series. By default is ./conf/WattWizard/time_series.",
        )

    def parse_args(self):
        args = self.parser.parse_args()
        self.args_dict = vars(args)
        return self.args_dict

    def get_args(self):
        return self.args_dict

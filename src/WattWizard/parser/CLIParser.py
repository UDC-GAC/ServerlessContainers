import argparse
from argparse import RawTextHelpFormatter


def parse_cores_distribution_to_dict(arg_str):
    arg_dict = {}
    cpus_str = arg_str.split(';')
    for cpu_str in cpus_str:
        cpu, cores = cpu_str.split('=')
        arg_dict[cpu] = cores
    return arg_dict


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
            "--server-mode",
            action="store_const",
            const=True,
            help="Create an API REST to access models in real time",
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
            "-s",
            "--structures",
            help="Comma-separated list of structures to build models for. Supported structures:\n\
    \tcontainer\t\t\tModel using container metrics\n\
    \thost\t\t\tModel using wide-system metrics",
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
            "--sockets",
            type=int,
            help="Number of sockets of the CPU to be modelled. Only used for HW aware models. \
More than two sockets is not yet supported.",
        )

        self.parser.add_argument(
            "--cores-distribution",
            type=parse_cores_distribution_to_dict,
            help="Cores distribution of the CPU to be modelled. Only used for HW aware models. \
Example: CPU0=0-15,32-47;CPU1=16-31,48-63",
        )

        self.parser.add_argument(
            "--csv-caching-train",
            action="store_const",
            const=True,
            help="Cache training time series in CSV files for future reuse",
        )

        self.parser.add_argument(
            "--csv-caching-test",
            action="store_const",
            const=True,
            help="Cache test time series in CSV files for future reuse",
        )

        self.parser.add_argument(
            "--join-train-timestamps",
            action="store_const",
            const=True,
            help="Get just the first start timestamp and the last stop timestamp from train timestamp files.",
        )

        self.parser.add_argument(
            "--train-timestamps-dir",
            help="Directory in which the timestamp files to train models are stored. By default is ./conf/WattWizard/timestamps/train.",
        )

        self.parser.add_argument(
            "--train-files",
            help="Comma-separated list of train file names stored under train timestamps directory (or 'all' keyword to use all files in this directory). \n\
One model per train file and prediction method will be created if possible. Each file must store time series timestamps from pretrain \n\
data in proper format. Check README.md to see timestamps proper format.",
        )

        self.parser.add_argument(
            "--join-test-timestamps",
            action="store_const",
            const=True,
            help="Get just the first start timestamp and the last stop timestamp from test timestamp files.",
        )

        self.parser.add_argument(
            "--test-timestamps-dir",
            help="Directory in which the timestamp files to test models are stored. By default is ./conf/WattWizard/timestamps/test.",
        )

        self.parser.add_argument(
            "--test-files",
            help="Comma-separated list of test file names stored under test timestamps directory (or 'all' keyword to use all files in this directory). \n\
Each file must store time series timestamps from test data in proper format. Check README.md to see timestamps proper format.",
        )

        self.parser.add_argument(
            "--plot-time-series",
            action="store_const",
            const=False,
            help="Plot the time series used to train and test each model",
        )

        self.parser.add_argument(
            "--plot-time-series-dir",
            help="Directory to store a plot of the train/tets time series for each model. Works together with option --plot-time-series. \n\
By default is ./conf/WattWizard/time_series.",
        )

    def parse_args(self):
        args = self.parser.parse_args()
        self.args_dict = vars(args)
        return self.args_dict

    def get_args(self):
        return self.args_dict

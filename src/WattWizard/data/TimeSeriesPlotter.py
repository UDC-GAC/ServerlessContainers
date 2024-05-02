import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, AutoDateLocator
from matplotlib.lines import Line2D

DEFAULT_LABELS = {
    "load": "Utilization (%)",
    "user_load": "User Utilization (%)",
    "system_load": "System Utilization (%)",
    "wait_load": "IO Wait Utilization (%)",
    "freq": "Avg Frequency (MHz)",
    "sumfreq": "Sum Frequency (MHz)",
    "temp": "Temperature Cº",
    "power": "Power Consumption (W)",
    "power_predicted": "Predicted Power Consumption (W)"
}

DEFAULT_COLORS = {
    "load": "#2b83ba",
    "user_load": "#2b83ba",
    "system_load": "#5e3c99",
    "wait_load": "#f781bf",
    "freq": "#d7191c",
    "sumfreq": "#d7191c",
    "temp": "#f781bf",
    "power": "#fdae61",
    "power_predicted": "#008837"
}

DEFAULT_MARKERS = {
    "load": "o",
    "user_load": "o",
    "system_load": "s",
    "wait_load": "d",
    "freq": "X",
    "sumfreq": "X",
    "temp": None,
    "power": None,
    "power_predicted": None
}


# TODO: Implement class to plot train time series
class TimeSeriesPlotter:

    output_dir = None

    def __init__(self, output_dir=None):
        self.output_dir = output_dir

    def set_output_dir(self, output_dir):
        self.output_dir = output_dir
        # TODO: Create dir or dirs if they doesn't exist

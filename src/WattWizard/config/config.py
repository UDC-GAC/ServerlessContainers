model_vars = None
prediction_methods = None
influxdb_bucket = None
verbose = None

model_instances = {}

train_files_models_map = {}

DEFAULT_MAX = float('1e+30')
cpu_limits = {
    "load": {"min": 0, "max": DEFAULT_MAX},
    "user_load": {"min": 0, "max": DEFAULT_MAX},
    "system_load": {"min": 0, "max": DEFAULT_MAX},
    "wait_load": {"min": 0, "max": DEFAULT_MAX},
    "freq": {"min": 0, "max": DEFAULT_MAX},
    "sumfreq": {"min": 0, "max": DEFAULT_MAX},
    "temp": {"min": 0, "max": DEFAULT_MAX}
}

SUPPORTED_VARS = ["load", "user_load", "system_load", "wait_load", "freq", "sumfreq", "temp"]
SUPPORTED_PRED_METHODS = ["mlpregressor", "sgdregressor", "polyreg"]
STATIC_METHODS = ["polyreg"]


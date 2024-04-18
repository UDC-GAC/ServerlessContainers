import os

USER_DIR = os.getcwd()
SCRIPT_PATH = os.path.abspath(__file__)
WATTWIZARD_DIR = os.path.dirname(os.path.dirname(SCRIPT_PATH))

COMMA_SEPARATED_LIST_ARGS = ['prediction_methods', 'model_variables', 'host_train_files', 'container_train_files']
DIRECTORY_ARGS = ['host_timestamps_dir', 'container_timestamps_dir']
FILE_ARGS = ['host_train_files', 'container_train_files']

DEFAULT_MAX_RESOURCE_LIMIT = float('1e+30')
DEFAULT_CPU_LIMITS = {
    "load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "user_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "system_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "wait_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "freq": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "sumfreq": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "temp": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT}
}


class MyConfig:

    __instance = None
    args = None
    cpu_limits = None

    @staticmethod
    def get_project_dir():
        return WATTWIZARD_DIR

    @staticmethod
    def get_instance():
        if MyConfig.__instance is None:
            MyConfig()
        return MyConfig.__instance

    def __init__(self):
        if MyConfig.__instance is not None:
            raise Exception(f"Trying to break Singleton. There is already an instance of {self.__class__.__name__} class")
        else:
            MyConfig.__instance = self

        self.args = {}
        self.cpu_limits = DEFAULT_CPU_LIMITS

    def set_resource_cpu_limit(self, resource, limit_type, value):
        if limit_type not in ["min", "max"]:
            raise Exception(f"Bad cpu limit type '{limit_type}' it must be 'min' or 'max'")
        if resource in self.cpu_limits:
            self.cpu_limits[resource][limit_type] = value
        else:
            raise Exception(f"Resource '{resource}' not found in cpu limits")

    def add_argument(self, arg_name, arg_value):
        if arg_name in COMMA_SEPARATED_LIST_ARGS:
            self.args[arg_name] = arg_value.split(',')
        else:
            self.args[arg_name] = arg_value

        if arg_name in DIRECTORY_ARGS:
            self.args[arg_name] = arg_value
            if arg_value.startswith("."):
                self.args[arg_name] = f"{USER_DIR}/{arg_value[2:]}"

        # Set full path for train timestamp files
        if arg_name in FILE_ARGS:
            if arg_name == "host_train_files":
                self.args[arg_name] = [f"{self.args['host_timestamps_dir']}/{f}.timestamps" if f != "NPT" else f for f in self.args[arg_name]]
            if arg_name == "container_train_files":
                self.args[arg_name] = [f"{self.args['container_timestamps_dir']}/{f}.timestamps" if f != "NPT" else f for f in self.args[arg_name]]

    def get_resource_cpu_limit(self, resource, limit_type):
        if limit_type not in ["min", "max"]:
            raise Exception(f"Bad cpu limit type '{limit_type}' it must be 'min' or 'max'")
        if resource in self.cpu_limits:
            return self.cpu_limits[resource][limit_type]
        raise Exception(f"Resource '{resource}' not found in cpu limits")

    def get_resource_cpu_limits(self, resource):
        if resource in self.cpu_limits:
            return self.cpu_limits[resource]
        raise Exception(f"Resource '{resource}' not found in cpu limits")

    def get_cpu_limits(self):
        return self.cpu_limits

    def get_argument(self, arg_name):
        if arg_name in self.args:
            return self.args[arg_name]
        return None

    def get_arguments(self):
        return self.args

    def get_summary(self):
        summary = []
        for arg_name in self.args:
            summary.append(f"{arg_name}: {self.args[arg_name]}")
        return summary

    def check_resources_limits(self, resources):
        for var in resources:
            value = resources[var]
            var_limits = self.get_resource_cpu_limits(var)
            if value < var_limits["min"]:
                raise ValueError(f'Too low {var} value ({value}). '
                                 f'Minimum value is {var_limits["min"]}.')
            if value > var_limits["max"]:
                raise ValueError(f'{var} value ({value}) exceeds its maximum. '
                                 f'Maximum value is {var_limits["max"]}.')

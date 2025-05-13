import os
import shutil

USER_DIR = os.getcwd()
SCRIPT_PATH = os.path.abspath(__file__)
WATTWIZARD_DIR = os.path.dirname(os.path.dirname(SCRIPT_PATH))

COMMA_SEPARATED_LIST_ARGS = ['structures', 'prediction_methods', 'model_variables', 'train_files', 'test_files']
DIRECTORY_ARGS = ['train_timestamps_dir', 'test_timestamps_dir', 'plot_time_series_dir']
FILE_ARGS = ['train_files', 'test_files']

DEFAULT_MAX_RESOURCE_LIMIT = float('1e+30')
DEFAULT_CPU_LIMITS = {
    "load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "user_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "system_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "p_user_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "p_system_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "l_user_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "l_system_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "wait_load": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "avgfreq": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "sumfreq": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "temp": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT},
    "power": {"min": 0, "max": DEFAULT_MAX_RESOURCE_LIMIT}
}


class MyConfig:
    __instance = None
    args = None
    cpu_limits = None

    def __init__(self):
        if MyConfig.__instance is not None:
            raise Exception(
                f"Trying to break Singleton. There is already an instance of {self.__class__.__name__} class")
        else:
            MyConfig.__instance = self

        self.args = {}
        self.cpu_limits = dict(DEFAULT_CPU_LIMITS)

    @staticmethod
    def get_instance():
        if MyConfig.__instance is None:
            MyConfig()
        return MyConfig.__instance

    @staticmethod
    def get_logo():
        return '''
        __          __   _   ___          ___                  _ 
        \\ \\        / /  | | | \\ \\        / (_)                | |
         \\ \\  /\\  / /_ _| |_| |\\ \\  /\\  / / _ ______ _ _ __ __| |
          \\ \\/  \\/ / _` | __| __\\ \\/  \\/ / | |_  / _` | '__/ _` |
           \\  /\\  / (_| | |_| |_ \\  /\\  /  | |/ / (_| | | | (_| |
            \\/  \\/ \\__,_|\\__|\\__| \\/  \\/   |_/___\\__,_|_|  \\__,_|
        '''

    @staticmethod
    def get_dashed_line():
        return "".join(["-" for _ in range(30, shutil.get_terminal_size(fallback=(120, 30)).columns)])

    @staticmethod
    def get_project_dir():
        return WATTWIZARD_DIR

    @staticmethod
    def get_file_paths(file_arg, timestamps_dir):
        # If the arg was an empty string no files are used
        if len(file_arg) == 1 and file_arg[0] == "":
            return []

        filenames = file_arg
        if len(file_arg) == 1 and file_arg[0] == "all":
            # If "all" is indicated, all the files in timestamps_dir is used
            filenames = [f for f in os.listdir(timestamps_dir) if f.endswith('.timestamps')]

        file_paths = []
        for name in filenames:
            # NPT stands for Not Pre-Trained: Useful to build models without a previous training
            if name == "NPT":
                file_paths.append(None)
                continue

            _, ext = os.path.splitext(name)
            if ext == '':
                name += ".timestamps"

            full_path = os.path.normpath(os.path.join(timestamps_dir, name))
            if os.path.isfile(full_path):
                file_paths.append(full_path)
            else:
                raise Exception(f"While building files list: File path {full_path} is not a valid file")

        return file_paths

    @staticmethod
    def convert_distribution_dict(dict_arg):
        new_dict = {}
        for cpu, ranges_str in dict_arg.items():
            result = []
            for r in ranges_str.split(','):
                if '-' in r:
                    start, end = map(int, r.split('-'))
                    result.extend([str(i) for i in range(start, end + 1)])
                else:
                    result.append(r)
            new_dict[cpu] = result
        return new_dict

    def get_summary(self):
        return [self.get_dashed_line(), "WATTWIZARD CONFIGURATION"] + [f"{k.upper() + ':':<30} {v}" for k, v in self.args.items()] + [self.get_dashed_line()]

    def set_resource_cpu_limit(self, resource, limit_type, value):
        if limit_type not in ["min", "max"]:
            raise Exception(f"Bad cpu limit type '{limit_type}' it must be 'min' or 'max'")
        if resource in self.cpu_limits:
            self.cpu_limits[resource][limit_type] = value
        else:
            raise Exception(f"Resource '{resource}' not found in cpu limits")

    def get_resource_cpu_limit(self, resource, limit_type):
        if limit_type not in ["min", "max"]:
            raise Exception(f"Bad cpu limit type '{limit_type}' it must be 'min' or 'max'")
        return self.get_resource_cpu_limits(resource)[limit_type]

    def get_resource_cpu_limits(self, resource):
        for key in self.cpu_limits:
            if resource.startswith(key):
                return self.cpu_limits[key]
        raise Exception(f"Resource starting with '{resource}' not found in cpu limits")

    def get_cpu_limits(self):
        return self.cpu_limits

    def add_argument(self, arg_name, arg_value):
        if arg_name in COMMA_SEPARATED_LIST_ARGS:
            arg_value = arg_value.split(',')

        if arg_name in DIRECTORY_ARGS and arg_value.startswith("./"):
            # Convert relative path to full path
            arg_value = os.path.normpath(os.path.join(USER_DIR, arg_value[2:]))

        if arg_name in FILE_ARGS:
            suffix = arg_name.split('_')[0]  # Train or test
            arg_value = self.get_file_paths(arg_value, self.args[f'{suffix}_timestamps_dir'])

        if arg_name == 'cores_distribution':
            arg_value = self.convert_distribution_dict(arg_value)

        self.args[arg_name] = arg_value

    def get_argument(self, arg_name):
        if arg_name in self.args:
            return self.args[arg_name]
        return None

    def get_arguments(self):
        return self.args

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

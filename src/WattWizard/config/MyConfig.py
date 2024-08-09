import os

USER_DIR = os.getcwd()
SCRIPT_PATH = os.path.abspath(__file__)
WATTWIZARD_DIR = os.path.dirname(os.path.dirname(SCRIPT_PATH))

COMMA_SEPARATED_LIST_ARGS = ['structures', 'prediction_methods', 'model_variables', 'train_files', 'test_files']
DIRECTORY_ARGS = ['train_timestamps_dir', 'test_timestamps_dir', 'plot_time_series_dir']
FILE_ARGS = ['train_files', 'test_files']
DICT_ARGS = ['cores_distribution']

DASHED_LINE = "".join(["-" for _ in range(1, 200)])

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
    def get_instance():
        if MyConfig.__instance is None:
            MyConfig()
        return MyConfig.__instance

    def __init__(self):
        if MyConfig.__instance is not None:
            raise Exception(
                f"Trying to break Singleton. There is already an instance of {self.__class__.__name__} class")
        else:
            MyConfig.__instance = self

        self.args = {}
        self.cpu_limits = DEFAULT_CPU_LIMITS

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
    def get_project_dir():
        return WATTWIZARD_DIR

    @staticmethod
    def adjust_filenames_list(filenames_list, timestamps_dir):
        if len(filenames_list) == 1 and filenames_list[0] == "":
            filenames_list = []
        if len(filenames_list) == 1 and filenames_list[0] == "all":
            filenames_list = [f for f in os.listdir(timestamps_dir) if f.endswith('.timestamps')]
        return filenames_list

    @staticmethod
    def get_files_list(filenames_list, timestamps_dir):
        files_list = []
        for filename in filenames_list:
            if filename != "NPT":
                _, extension = os.path.splitext(filename)
                if extension == '':
                    filename += ".timestamps"

                file = f"{timestamps_dir}/{filename}"
                if os.path.isfile(file):
                    files_list.append(file)
                else:
                    raise Exception(f"While making files list: File path {file} is not a file")
            else:
                files_list.append("NPT")
        return files_list

    @staticmethod
    def convert_distribution_dict(dict_arg):
        new_dict = {}
        for cpu, ranges_str in dict_arg.items():
            result = []
            for r in ranges_str.split(','):
                if '-' in r:
                    start, end = map(int, r.split('-'))
                    result.extend(range(start, end + 1))
                else:
                    result.append(int(r))
            new_dict[cpu] = result
        return new_dict

    def set_resource_cpu_limit(self, resource, limit_type, value):
        if limit_type not in ["min", "max"]:
            raise Exception(f"Bad cpu limit type '{limit_type}' it must be 'min' or 'max'")
        if resource in self.cpu_limits:
            self.cpu_limits[resource][limit_type] = value
        else:
            raise Exception(f"Resource '{resource}' not found in cpu limits")

    def add_argument(self, arg_name, arg_value):
        if arg_name in COMMA_SEPARATED_LIST_ARGS:
            arg_value = arg_value.split(',')

        if arg_name in DICT_ARGS:
            arg_value = self.convert_distribution_dict(arg_value)

        if arg_name in DIRECTORY_ARGS and arg_value.startswith("."):
            # Convert relative path to full path
            self.args[arg_name] = f"{USER_DIR}/{arg_value[2:]}"

        elif arg_name in FILE_ARGS:
            suffix = arg_name.split('_')[0]  # Train or test
            # Set full path for timestamp files
            filenames_list = self.adjust_filenames_list(arg_value, self.args[f"{suffix}_timestamps_dir"])
            self.args[arg_name] = self.get_files_list(filenames_list, self.args[f"{suffix}_timestamps_dir"])
        else:
            self.args[arg_name] = arg_value

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
        summary = [DASHED_LINE]
        summary.append("WATTWIZARD CONFIGURATION")
        for arg_name in self.args:
            summary.append(f"{arg_name}: {self.args[arg_name]}")
        summary.append(DASHED_LINE)
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

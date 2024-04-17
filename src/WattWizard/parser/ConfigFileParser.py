import yaml
import os

from src.WattWizard.logs.logger import log
from src.WattWizard.config.MyConfig import MyConfig

WATTWIZARD_DIR = MyConfig.get_project_dir()
CONFIG_FILE = f"{WATTWIZARD_DIR}/config.yml"


class ConfigFileParser:

    def __init__(self, config_file=None):
        self.config_file = CONFIG_FILE
        if config_file is not None:
            self.config_file = config_file
        self.args_dict = None

    def parse_args(self):
        if os.path.isfile(self.config_file) and os.access(self.config_file, os.R_OK):
            with open(self.config_file, "r") as f:
                self.args_dict = yaml.load(f, Loader=yaml.FullLoader)
        else:
            log(f"Configuration file: {self.config_file} doesn't exists", "ERR")
            exit(1)
        return self.args_dict

    def get_args(self):
        return self.args_dict

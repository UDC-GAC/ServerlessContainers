import json
import requests
import yaml
import os


class WattWizardUtils:
    __WATTWIZARD_URL = "wattwizard"
    __WATTWIZARD_PORT = 7777

    def __init__(self, wattwizard_url=None, wattwizard_port=None):

        serverless_path = os.environ['SERVERLESS_PATH']
        config_file = serverless_path + "/services_config.yml"
        with open(config_file, "r") as f:
            config = yaml.load(f, Loader=yaml.FullLoader)

        if not wattwizard_url:
            wattwizard_url = config['WATTWIZARD_URL']
        if not wattwizard_port:
            wattwizard_port = config['WATTWIZARD_PORT']
        else:
            try:
                wattwizard_port = int(wattwizard_port)
            except ValueError:
                wattwizard_port = self.__WATTWIZARD_PORT

        self.server = "http://{0}:{1}".format(wattwizard_url, str(wattwizard_port))
        self.session = requests.Session()

    def close_connection(self):
        self.session.close()

    def get_power_from_usage(self, model_name, user_usage, system_usage, power_target, tries=3):
        try:
            params = {'user_load': user_usage, 'system_load': system_usage, 'desired_power': power_target}
            r = self.session.get("{0}/{1}/{2}".format(self.server, "inverse-predict", model_name), params=params)
            if r.status_code == 200:
                return r.json()['user_load']
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise e
            else:
                self.get_power_from_usage(model_name, user_usage, system_usage, power_target, tries)

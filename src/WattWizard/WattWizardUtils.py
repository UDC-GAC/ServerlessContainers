import requests
import json
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
            wattwizard_url = config['WATT_WIZARD_URL']
        if not wattwizard_port:
            wattwizard_port = config['WATT_WIZARD_PORT']
        else:
            try:
                wattwizard_port = int(wattwizard_port)
            except ValueError:
                wattwizard_port = self.__WATTWIZARD_PORT

        self.server = "http://{0}:{1}".format(wattwizard_url, str(wattwizard_port))
        self.session = requests.Session()

    def close_connection(self):
        self.session.close()

    def get_usage_from_power(self, structure, model_name, user_usage, system_usage, power_target, tries=3):
        try:
            params = {'user_load': user_usage, 'system_load': system_usage, 'desired_power': power_target}
            r = self.session.get("{0}/{1}/{2}/{3}".format(self.server, "inverse-predict", structure, model_name), params=params)
            if r.status_code == 200:
                return r.json()['user_load']
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise e
            else:
                self.get_usage_from_power(structure, model_name, user_usage, system_usage, power_target, tries)

    def get_idle_consumption(self, structure, model_name, tries=3):
        try:
            r = self.session.get("{0}/{1}/{2}/{3}".format(self.server, "idle-consumption", structure, model_name))
            if r.status_code == 200:
                return r.json()['idle_consumption']
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise e
            else:
                self.get_idle_consumption(structure, model_name, tries)

    def train_model(self, structure, model_name, user_usage, system_usage, power, tries=3):
        try:
            payload = {'user_load': user_usage, 'system_load': system_usage, 'power': power}
            r = self.session.post("{0}/{1}/{2}/{3}".format(self.server, "train", structure, model_name), json=json.dumps(payload))

            if r.status_code == 200:
                return r.json()
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise e
            else:
                self.train_model(structure, model_name, user_usage, system_usage, power, tries)

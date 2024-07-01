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

    def is_static(self, structure, model_name, tries=3):
        try:
            r = self.session.get("{0}/{1}/{2}/{3}".format(self.server, "is-static", structure, model_name))
            if r.status_code == 200:
                return r.json()['is_static']
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.is_static(structure, model_name, tries)

    def get_usage_meeting_budget(self, structure, model_name, user_usage, system_usage, power_budget, tries=3):
        try:
            params = {'user_load': user_usage,
                      'system_load': system_usage,
                      'desired_power': power_budget}
            r = self.session.get("{0}/{1}/{2}/{3}".format(self.server, "inverse-predict", structure, model_name), params=params)
            if r.status_code == 200:
                return r.json()
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.get_usage_meeting_budget(structure, model_name, user_usage, system_usage, power_budget, tries)

    def get_adjusted_usage_meeting_budget(self, structure, model_name, user_usage, system_usage, real_power, power_budget, tries=3):
        try:
            params = {'user_load': user_usage,
                      'system_load': system_usage,
                      'real_power': real_power,
                      'desired_power': power_budget}
            r = self.session.get("{0}/{1}/{2}/{3}".format(self.server, "adjusted-inverse-predict", structure, model_name), params=params)
            if r.status_code == 200:
                return r.json()
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.get_usage_meeting_budget(structure, model_name, user_usage, system_usage, power_budget, tries)

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
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.get_idle_consumption(structure, model_name, tries)

    def get_models(self, avoid_static=False, tries=3):
        try:
            params = {'avoid-static': 'true' if avoid_static else 'false'}
            r = self.session.get("{0}/{1}".format(self.server, "models"), params=params)

            if r.status_code == 200:
                return r.json()
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.get_models(avoid_static, tries)

    def get_models_structure(self, structure, avoid_static=False, tries=3):
        try:
            params = {'avoid-static': 'true' if avoid_static else 'false'}
            r = self.session.get("{0}/{1}/{2}".format(self.server, "models", structure), params=params)

            if r.status_code == 200:
                return r.json()
            else:
                r.raise_for_status()
        except requests.ConnectionError as e:
            tries -= 1
            if tries <= 0:
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.get_models_structure(structure, avoid_static, tries)

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
                raise Exception(f"Failed to connect to WattWizard: {str(e)}") from e
            else:
                self.train_model(structure, model_name, user_usage, system_usage, power, tries)

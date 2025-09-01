#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

from threading import Thread
import requests
import time
import traceback

import src.MyUtils.MyUtils as utils
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service


BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'structure.energy.usage']

WATT_TRAINER_METRICS = {
    'cpu_user': ['proc.cpu.user'],
    'cpu_kernel': ['proc.cpu.kernel'],
    'energy': ['structure.energy.usage']
}

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10, "USAGE_THRESHOLD": 1.0,
                         "TRAIN_METRICS": ["cpu_user", "cpu_kernel", "energy"],
                         "MODELS_TO_TRAIN": ["all"], "DEBUG": True, "ACTIVE": True}


class WattTrainer(Service):
    """ WattTrainer class that implements all the logic for this service"""

    def __init__(self):
        super().__init__("watt_trainer", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="window_timelapse")
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.window_timelapse, self.window_delay, self.usage_threshold, self.train_metrics = None, None, None, None
        self.prev_models_to_train, self.models_to_train, self.debug, self.active,  = None, None, None, None

    def get_container_usages(self, container_name):
        success = False
        try:
            container_info = self.opentsdb_handler.get_structure_timeseries({"host": container_name},
                                                                            self.window_timelapse,
                                                                            self.window_delay,
                                                                            BDWATCHDOG_METRICS,
                                                                            WATT_TRAINER_METRICS)
            for metric in WATT_TRAINER_METRICS:
                if metric not in self.train_metrics:
                    continue
                if container_info[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE:
                    utils.log_warning("No info for {0} in container {1}".format(metric, container_name), debug=self.debug)
                    return False, {}

            success = container_info["cpu_user"] > self.usage_threshold or \
                      container_info["cpu_kernel"] > self.usage_threshold

        except requests.ConnectionError as e:
            utils.log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=self.debug)
            raise e

        return success, container_info

    def train_model(self, structure, structure_type, model_name, usages):
        missing_values = False
        for resource in self.train_metrics:
            if resource not in usages:
                missing_values = True
                utils.log_error(
                    "Missing {0} value for structure {1} to train model {2}".format(resource, structure, model_name),
                    debug=self.debug)

        if not missing_values:
            try:
                r = self.wattwizard_handler.train_model(structure_type,
                                                        model_name,
                                                        [usages['cpu_user']],
                                                        [usages['cpu_kernel']],
                                                        [usages['energy']])
                utils.log_info("Structure = {0} | Model name = {1} | Msg = {2}".format(structure, model_name, r["INFO"]),
                               self.debug)
            except Exception as e:
                utils.log_error(str(e), debug=self.debug)

    def train_models_with_containers_info(self, containers):
        for container in containers:
            success, container_usages = self.get_container_usages(container["name"])
            if success:
                for model in self.models_to_train:
                    self.train_model(container["name"], "host", model, container_usages)

    def train_thread(self):
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        if containers:
            self.train_models_with_containers_info(containers)

    def check_models_to_train(self, current_models_to_train):
        # Models to train has been changed
        if current_models_to_train != self.prev_models_to_train:
            try:
                self.prev_models_to_train = current_models_to_train
                if len(current_models_to_train) == 1 and current_models_to_train[0] == "all":
                    # Train all available non-static models
                    return self.wattwizard_handler.get_models_structure("host", avoid_static=True)

                else:
                    # Train all specified non-static models
                    models_to_train = []
                    for model in current_models_to_train:
                        if not self.wattwizard_handler.is_static("host", model):
                            models_to_train.append(model)
                        else:
                            utils.log_warning(
                                "Model {0} uses a static prediction method, it can't be retrained, ignoring".format(model),
                                debug=self.debug)
                    return models_to_train

            except Exception as e:
                utils.log_warning("Some problem ocurred checking models to train, "
                                  "probably connecting to WattWizard: {0}".format(str(e)), self.debug)
                self.prev_models_to_train = None
                return []

        # If no changes we return the list already used in previous iteration
        return self.models_to_train

    def invalid_conf(self, service_config):
        for metric in self.train_metrics:
            if metric not in {"cpu_user", "cpu_kernel", "energy"}:
                return True, "Train metrics value '{0}' is invalid".format(self.train_metrics)

        return self.config_validator.invalid_conf(service_config)

    def work(self, ):
        thread = None
        containers = utils.get_structures(self.couchdb_handler, self.debug, subtype="container")
        if len(self.models_to_train) == 0:
            # Models to train couldn't be checked
            utils.log_info("No models to train", self.debug)
        elif not containers:
            # As no container info is available, models can't be trained
            utils.log_info("No structures to process", self.debug)
        else:
            thread = Thread(target=self.train_thread, args=())
            thread.start()
            utils.log_info("Model trained", self.debug)
        return thread

    def train(self, ):
        self.run_loop()


def main():
    try:
        watt_trainer = WattTrainer()
        watt_trainer.train()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

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
import logging

from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    get_structures, wait_operation_thread, end_epoch, start_epoch
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog
import src.WattWizard.WattWizardUtils as wattwizard

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.cpu.kernel', 'structure.energy.usage']

WATT_TRAINER_METRICS = {
    'cpu_user': ['proc.cpu.user'],
    'cpu_kernel': ['proc.cpu.kernel'],
    'energy': ['structure.energy.usage']
}

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 10, "WINDOW_DELAY": 10,
                         "GENERATED_METRICS": ["cpu_user", "cpu_kernel", "energy"],
                         "MODELS_TO_TRAIN": ["sgdregressor_General"], "DEBUG": True, "ACTIVE": True}

SERVICE_NAME = "watt_trainer"


class WattTrainer:
    """ WattTrainer class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.wattwizard_handler = wattwizard.WattWizardUtils()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.config = MyConfig(CONFIG_DEFAULT_VALUES)
        self.debug = True

    def get_container_usages(self, container_name):
        try:
            container_info = self.opentsdb_handler.get_structure_timeseries({"host": container_name},
                                                                            self.window_difference,
                                                                            self.window_delay,
                                                                            BDWATCHDOG_METRICS,
                                                                            WATT_TRAINER_METRICS)
            for metric in WATT_TRAINER_METRICS:
                if metric not in self.config.get_value("GENERATED_METRICS"):
                    continue
                if container_info[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE:
                    log_warning("No info for {0} in container {1}".format(metric, container_name), debug=self.debug)

        except requests.ConnectionError as e:
            log_error("Connection error: {0} {1}".format(str(e), str(traceback.format_exc())), debug=self.debug)
            raise e

        return container_info

    def train_model(self, structure, structure_type, model_name, usages):
        missing_values = False
        for resource in self.config.get_value("GENERATED_METRICS"):
            if resource not in usages:
                missing_values = True
                log_error("Missing {0} value for structure {1} to train model {2}".format(resource, structure, model_name), debug=self.debug)

        if not missing_values:
            try:
                r = self.wattwizard_handler.train_model(structure_type,
                                                        model_name,
                                                        [usages['cpu_user']],
                                                        [usages['cpu_kernel']],
                                                        [usages['energy']])
                log_info("Structure = {0} | Model name = {1} | Msg = {2}".format(structure, model_name, r["INFO"]), self.debug)
            except Exception as e:
                log_error(str(e), debug=self.debug)

    def train_model_with_containers_info(self, containers):
        for container in containers:
            container_usages = self.get_container_usages(container["name"])
            for model in self.models_to_train:
                if not self.wattwizard_handler.is_static("container", model):
                    self.train_model(container["name"], "container", model, container_usages)
                else:
                    log_warning("Model {0} uses a static prediction method, it can't be retrained, ignoring".format(model), debug=self.debug)

    def train_thread(self, ):
        containers = get_structures(self.couchdb_handler, self.debug, subtype="container")
        if containers:
            self.train_model_with_containers_info(containers)

    def train(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

        while True:
            # Get service info
            service = get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            self.config.set_config(service["config"])
            self.debug = self.config.get_value("DEBUG")
            self.window_difference = self.config.get_value("WINDOW_TIMELAPSE")
            self.window_delay = self.config.get_value("WINDOW_DELAY")
            self.models_to_train = self.config.get_value("MODELS_TO_TRAIN")
            SERVICE_IS_ACTIVATED = self.config.get_value("ACTIVE")

            t0 = start_epoch(self.debug)

            log_info("Config is as follows:", self.debug)
            log_info(".............................................", self.debug)
            log_info("Models to train -> {0}".format(self.models_to_train), self.debug)
            log_info("Time window lapse -> {0}".format(self.window_difference), self.debug)
            log_info("Delay -> {0}".format(self.window_delay), self.debug)
            log_info(".............................................", self.debug)

            thread = None
            if SERVICE_IS_ACTIVATED:
                # Remote database operation
                containers = get_structures(self.couchdb_handler, self.debug, subtype="container")
                if not containers:
                    # As no container info is available, models can't be trained
                    log_info("No structures to process", self.debug)
                    time.sleep(self.window_difference)
                    end_epoch(self.debug, self.window_difference, t0)
                    continue
                else:
                    thread = Thread(target=self.train_thread, args=())
                    thread.start()
            else:
                log_warning("WattTrainer is not activated", self.debug)
                continue

            time.sleep(self.window_difference)

            wait_operation_thread(thread, self.debug)
            log_info("Model trained", self.debug)

            end_epoch(self.debug, self.window_difference, t0)


def main():
    try:
        watt_trainer = WattTrainer()
        watt_trainer.train()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

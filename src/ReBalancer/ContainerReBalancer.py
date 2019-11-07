# Copyright (c) 2019 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
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

import time
import traceback

import requests
from json_logic import jsonLogic

from src.MyUtils import MyUtils
from src.ReBalancer.Utils import CONFIG_DEFAULT_VALUES, app_can_be_rebalanced
from src.StateDatabase import opentsdb
from src.StateDatabase import couchdb

BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.cpu.kernel']
GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel']}


class ContainerRebalancer:
    def __init__(self):
        self.__opentsdb_handler = opentsdb.OpenTSDBServer()
        self.__couchdb_handler = couchdb.CouchDBServer()
        self.__NO_METRIC_DATA_DEFAULT_VALUE = self.__opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.__debug = True
        self.__config = {}

    # @staticmethod
    # def __generate_request(structure_name, amount, resource, action):
    #     request = dict(
    #         type="request",
    #         resource=resource,
    #         amount=int(amount),
    #         structure=structure_name,
    #         action=action,
    #         timestamp=int(time.time()))
    #     return request

    def __get_container_usages(self, container):
        window_difference = MyUtils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")

        try:
            # Remote database operation
            usages = self.__opentsdb_handler.get_structure_timeseries({"host": container["name"]},
                                                                      window_difference,
                                                                      window_delay,
                                                                      BDWATCHDOG_CONTAINER_METRICS,
                                                                      GUARDIAN_CONTAINER_METRICS)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.__NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                MyUtils.log_warning("container: {0} has no usage data".format(container["name"]), self.__debug)
                return None

            return usages
        except Exception as e:
            MyUtils.log_error(
                "error with structure: {0} {1} {2}".format(container["name"], str(e), str(traceback.format_exc())),
                self.__debug)

            return None

    def __fill_containers_with_usage_info(self, containers):
        # Get the usages
        containers_with_resource_usages = list()
        for container in containers:
            usages = self.__get_container_usages(container)
            if usages:
                for usage_metric in usages:
                    keys = usage_metric.split(".")
                    # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
                    container["resources"][keys[1]][keys[2]] = usages[usage_metric]
                containers_with_resource_usages.append(container)
        return containers_with_resource_usages

    def __rebalance_containers_by_pair_swapping(self, containers, app_name):
        # Filter the containers between donors and receivers, according to usage and rules
        donors, receivers = list(), list()
        for container in containers:
            try:
                data = {"cpu": {"structure": {"cpu": {
                    "usage": container["resources"]["cpu"]["usage"],
                    "min": container["resources"]["cpu"]["min"],
                    "max": container["resources"]["cpu"]["max"],
                    "current": container["resources"]["cpu"]["current"]}}}}
            except KeyError:
                continue

            # containers that have low resource usage (donors)
            rule_low_usage = self.__couchdb_handler.get_rule("cpu_usage_low")
            if jsonLogic(rule_low_usage["rule"], data):
                donors.append(container)

            # containers that have a bottleneck (receivers)
            rule_high_usage = self.__couchdb_handler.get_rule("cpu_usage_high")
            if jsonLogic(rule_high_usage["rule"], data):
                receivers.append(container)

        if not receivers:
            MyUtils.log_info("No containers in need of rebalancing for {0}".format(app_name), self.__debug)
            return
        else:
            # Order the containers from lower to upper current CPU limit
            containers_to_give = sorted(receivers, key=lambda c: c["resources"]["cpu"]["current"])

        # MyUtils.log_info("Nodes to steal from {0}".format(str([c["name"] for c in containers_to_steal])), self.debug)
        # MyUtils.log_info("Nodes to give to {0}".format(str([c["name"] for c in containers_to_give])), self.debug)

        # Steal resources from the low-usage containers
        shuffling_tuples = list()
        for container in donors:
            # Ensure that this request will be successfully processed, otherwise we are 'giving' away
            # extra resources

            stolen_amount = 0.7 * \
                            (container["resources"]["cpu"]["current"] - max(container["resources"]["cpu"]["min"],
                                                                            container["resources"]["cpu"]["usage"]))
            shuffling_tuples.append((container, stolen_amount))
        shuffling_tuples = sorted(shuffling_tuples, key=lambda c: c[1])

        # Give the resources to the bottlenecked containers
        for receiver in containers_to_give:

            if shuffling_tuples:
                donor, amount_to_scale = shuffling_tuples.pop(0)
            else:
                MyUtils.log_info("No more donors, container {0} left out".format(receiver["name"]), self.__debug)
                continue

            scalable_amount = receiver["resources"]["cpu"]["max"] - receiver["resources"]["cpu"]["current"]
            # If this container can't be scaled anymore, skip
            if scalable_amount == 0:
                continue

            # Trim the amount to scale if needed
            if amount_to_scale > scalable_amount:
                amount_to_scale = scalable_amount

            # Create the pair of scaling requests
            # TODO This should use Guardians method to generate requests
            request = dict(
                type="request",
                resource="cpu",
                amount=int(amount_to_scale),
                structure=receiver["name"],
                action="CpuRescaleUp",
                timestamp=int(time.time()),
                structure_type="container",
                host=receiver["host"],
                host_rescaler_ip=receiver["host_rescaler_ip"],
                host_rescaler_port=receiver["host_rescaler_port"]
            )
            self.__couchdb_handler.add_request(request)
            # TODO This should use Guardians method to generate requests
            request = dict(
                type="request",
                resource="cpu",
                amount=int(-amount_to_scale),
                structure=donor["name"],
                action="CpuRescaleDown",
                timestamp=int(time.time()),
                structure_type="container",
                host=donor["host"],
                host_rescaler_ip=donor["host_rescaler_ip"],
                host_rescaler_port=donor["host_rescaler_port"]
            )
            self.__couchdb_handler.add_request(request)

            MyUtils.log_info(
                "Resource swap between {0}(donor) and {1}(receiver)".format(donor["name"], receiver["name"]),
                self.__debug)

    def __app_containers_can_be_rebalanced(self, application):
        return app_can_be_rebalanced(application, "container", self.__couchdb_handler)

    def rebalance_containers(self, config):
        self.__config = config
        self.__debug = MyUtils.get_config_value(self.__config, CONFIG_DEFAULT_VALUES, "DEBUG")

        MyUtils.log_info("_______________", self.__debug)
        MyUtils.log_info("Performing CONTAINER CPU Balancing", self.__debug)

        # Get the containers and applications
        try:
            applications = MyUtils.get_structures(self.__couchdb_handler, self.__debug, subtype="application")
            containers = MyUtils.get_structures(self.__couchdb_handler, self.__debug, subtype="container")
        except requests.exceptions.HTTPError as e:
            MyUtils.log_error("Couldn't get applications", self.__debug)
            MyUtils.log_error(str(e), self.__debug)
            return

        # Filter out the ones that do not accept rebalancing or that do not need any internal rebalancing
        rebalanceable_apps = list()
        for app in applications:
            # TODO Improve this management
            if "rebalance" not in app or app["rebalance"] == True:
                pass
            else:
                continue
            if len(app["containers"]) <= 1:
                continue

            if self.__app_containers_can_be_rebalanced(app):
                rebalanceable_apps.append(app)

        # Sort them according to each application they belong
        app_containers = dict()
        for app in rebalanceable_apps:
            app_name = app["name"]
            app_containers[app_name] = list()
            app_containers_names = app["containers"]
            for container in containers:
                if container["name"] in app_containers_names:
                    app_containers[app_name].append(container)
            # Get the container usages
            app_containers[app_name] = self.__fill_containers_with_usage_info(app_containers[app_name])

        # Rebalance applications
        for app in rebalanceable_apps:
            app_name = app["name"]
            MyUtils.log_info("Going to rebalance {0} now".format(app_name), self.__debug)
            self.__rebalance_containers_by_pair_swapping(app_containers[app_name], app_name)

        MyUtils.log_info("_______________", self.__debug)
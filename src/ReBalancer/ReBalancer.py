# /usr/bin/python
from __future__ import print_function

from threading import Thread
import time
import traceback
import logging
from json_logic import jsonLogic

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as bdwatchdog

BDWATCHDOG_CONTAINER_METRICS = ['proc.cpu.user', 'proc.cpu.kernel']
GUARDIAN_CONTAINER_METRICS = {
    'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel']}

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE": 30,
                         "WINDOW_DELAY": 10,
                         "DEBUG": True}

SERVICE_NAME = "rebalancer"

SHARE_SHUFFLING_AMOUNT = 25


class ReBalancer:
    """ ReBalancer class that implements all the logic for this service"""

    def __init__(self):
        self.opentsdb_handler = bdwatchdog.OpenTSDBServer()
        self.couchdb_handler = couchdb.CouchDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.debug = True

    @staticmethod
    def generate_request(structure_name, amount, resource, action):
        request = dict(
            type="request",
            resource=resource,
            amount=int(amount),
            structure=structure_name,
            action=action,
            timestamp=int(time.time()))
        return request

    def get_container_usages(self, container, config):
        window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
        window_delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_DELAY")

        try:

            # Remote database operation
            usages = self.opentsdb_handler.get_structure_timeseries({"host": container["name"]}, window_difference,
                                                                    window_delay,
                                                                    BDWATCHDOG_CONTAINER_METRICS,
                                                                    GUARDIAN_CONTAINER_METRICS)

            # Skip this structure if all the usage metrics are unavailable
            if all([usages[metric] == self.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
                MyUtils.log_warning("container: {0} has no usage data".format(container["name"]), self.debug)
                return None

            return usages
        except Exception as e:
            MyUtils.log_error(
                "error with structure: {0} {1} {2}".format(container["name"], str(e), str(traceback.format_exc())),
                self.debug)

            return None

    def rebalance_containers(self, config, containers, app_name):
        # Get the usages
        containers_with_resource_usages = list()
        for container in containers:
            usages = self.get_container_usages(container, config)
            if usages:
                for usage_metric in usages:
                    keys = usage_metric.split(".")
                    # Split the key from the retrieved data, e.g., structure.mem.usages, where mem is the resource
                    container["resources"][keys[1]][keys[2]] = usages[usage_metric]
                containers_with_resource_usages.append(container)
        containers = containers_with_resource_usages

        # Filter the containers according to usage and rules
        containers_to_steal = list()
        containers_to_give = list()
        for container in containers:
            data = {"cpu": {"structure": {"cpu": {
                "usage": container["resources"]["cpu"]["usage"],
                "min": container["resources"]["cpu"]["min"],
                "max": container["resources"]["cpu"]["max"],
                "current": container["resources"]["cpu"]["current"]}}}}

            # containers that have low resource usage
            rule_low_usage = self.couchdb_handler.get_rule("cpu_usage_low")
            if (jsonLogic(rule_low_usage["rule"], data)):
                containers_to_steal.append(container)

            # containers that have a bottleneck
            rule_high_usage = self.couchdb_handler.get_rule("cpu_usage_high")
            if (jsonLogic(rule_high_usage["rule"], data)):
                containers_to_give.append(container)

        if not containers_to_give:
            MyUtils.log_info("No containers in need of rebalancing for {0}".format(app_name), self.debug)
            return
        else:
            # Order the containers from min to max
            ordenerd_containers = sorted(containers_to_give, key=lambda c: c["resources"]["cpu"]["current"])
            containers_to_give = ordenerd_containers

        MyUtils.log_info("Nodes to steal from {0}".format(str([c["name"] for c in containers_to_steal])), self.debug)
        MyUtils.log_info("Nodes to give to {0}".format(str([c["name"] for c in containers_to_give])), self.debug)

        # Steal resources uniformely from the low-usage containers
        amount_stolen = 0
        for container in containers_to_steal:
            # Ensure that this request will be successfully processed, otherwise we are 'giving' away
            # extra resources
            request = dict(
                type="request",
                resource="cpu",
                amount=int(-SHARE_SHUFFLING_AMOUNT),
                structure=container["name"],
                action="CpuRescaleDown",
                timestamp=int(time.time())
            )
            request["host"] = container["host"]
            request["host_rescaler_ip"] = container["host_rescaler_ip"]
            request["host_rescaler_port"] = container["host_rescaler_port"]
            self.couchdb_handler.add_request(request)
            amount_stolen += SHARE_SHUFFLING_AMOUNT

        # Give the resources uniformely to the bottlenecked containers
        scaling_mounts = dict()
        for container in containers_to_give:
            scaling_mounts[container["name"]] = 0
        while amount_stolen > 0:
            for container in containers_to_give:
                if amount_stolen >= SHARE_SHUFFLING_AMOUNT:
                    amount_to_give = SHARE_SHUFFLING_AMOUNT
                    amount_stolen -= SHARE_SHUFFLING_AMOUNT
                else:
                    amount_to_give = amount_stolen
                    amount_stolen = 0

                if amount_to_give > 0:
                    scaling_mounts[container["name"]] += amount_to_give

        # Generate the rescaling requests
        for container in containers_to_give:
            if container["name"] in scaling_mounts:
                amount_to_scale = scaling_mounts[container["name"]]
                scalable_amount = container["resources"]["cpu"]["max"] - container["resources"]["cpu"]["current"]

                # If this container can't be scaled anymore, skip
                if scalable_amount == 0 or amount_to_scale == 0:
                    continue

                # Trim the amount to scale if needed
                if amount_to_scale > scalable_amount:
                    amount_to_scale = scalable_amount
                    remaining_amount = amount_to_scale - scalable_amount

                request = dict(
                    type="request",
                    resource="cpu",
                    amount=int(amount_to_scale),
                    structure=container["name"],
                    action="CpuRescaleUp",
                    timestamp=int(time.time())
                )
                request["host"] = container["host"]
                request["host_rescaler_ip"] = container["host_rescaler_ip"]
                request["host_rescaler_port"] = container["host_rescaler_port"]
                self.couchdb_handler.add_request(request)

    def app_can_be_rebalanced(self, application):
        data = {"energy":
                    {"structure":
                         {"energy":
                              {"usage": application["resources"]["energy"]["usage"],
                               "max": application["resources"]["energy"]["max"]}}
                     },
                "cpu":
                    {"structure":
                         {"cpu":
                              {"usage": application["resources"]["cpu"]["usage"],
                               "min": application["resources"]["cpu"]["min"],
                               "current": application["resources"]["cpu"]["current"]}}
                     }
                }

        # Application is underusing energy, let the Guardian deal with it
        rule_low_usage = self.couchdb_handler.get_rule("energy_exceeded_upper")
        if jsonLogic(rule_low_usage["rule"], data):
            return False

        # Application is overusing energy, let the Guardian deal with it
        rule_high_usage = self.couchdb_handler.get_rule("energy_dropped_lower")
        if jsonLogic(rule_high_usage["rule"], data):
            return False

        # The application is in the middle area of using, check if container are balanced
        return True

    def rebalance(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
        while True:

            # Get service info
            service = MyUtils.get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            MyUtils.beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            config = service["config"]
            self.debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
            window_difference = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")
            thread = None

            # Remote database operation
            structures = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype="container")
            if structures:
                # Check if rebalancing of containers is needed
                applications = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype="application")
                for app in applications:
                    if self.app_can_be_rebalanced(app):
                        app_containers = list()
                        app_containers_names = app["containers"]
                        for container in structures:
                            if container["name"] in app_containers_names:
                                app_containers.append(container)

                        MyUtils.log_info("Going to rebalance {0} now".format(app["name"]), self.debug)
                        # Rebalance
                        # TODO FIX only pass the application's structures, not all of them
                        thread = Thread(target=self.rebalance_containers, args=(config, app_containers, app["name"]))
                        thread.start()
                    else:
                        MyUtils.log_info("Not rebalancing now", self.debug)

            MyUtils.log_info(
                "Epoch processed at {0}".format(MyUtils.get_time_now_string()), self.debug)
            time.sleep(window_difference)

            if thread and thread.isAlive():
                delay_start = time.time()
                MyUtils.log_warning(
                    "Previous thread didn't finish before next poll is due, with window time of " +
                    "{0} seconds, at {1}".format(str(window_difference), MyUtils.get_time_now_string()), self.debug)
                MyUtils.log_warning("Going to wait until thread finishes before proceeding", self.debug)
                thread.join()
                delay_end = time.time()
                MyUtils.log_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)),
                                    self.debug)


def main():
    try:
        rebalancer = ReBalancer()
        rebalancer.rebalance()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

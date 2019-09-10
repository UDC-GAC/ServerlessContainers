# /usr/bin/python
from __future__ import print_function

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
                         "SHARE_SHUFFLING_AMOUNT": 50,
                         "DEBUG": True}

SERVICE_NAME = "rebalancer"


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
            usages = self.opentsdb_handler.get_structure_timeseries({"host": container["name"]},
                                                                    window_difference,
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

    def fill_containers_with_usage_info(self, containers, config):
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
        return containers_with_resource_usages

    def rebalance_containers_by_pair_swapping(self, containers, app_name):
        # Filter the containers between donors and receivers, according to usage and rules
        donors = list()
        receivers = list()
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
            rule_low_usage = self.couchdb_handler.get_rule("cpu_usage_low")
            if jsonLogic(rule_low_usage["rule"], data):
                donors.append(container)

            # containers that have a bottleneck (receivers)
            rule_high_usage = self.couchdb_handler.get_rule("cpu_usage_high")
            if jsonLogic(rule_high_usage["rule"], data):
                receivers.append(container)

        if not receivers:
            MyUtils.log_info("No containers in need of rebalancing for {0}".format(app_name), self.debug)
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
                MyUtils.log_info("No more donors, container {0} left out".format(receiver["name"]), self.debug)
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
            self.couchdb_handler.add_request(request)
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
            self.couchdb_handler.add_request(request)

            MyUtils.log_info(
                "Resource swap between {0}(donor) and {1}(receiver)".format(donor["name"], receiver["name"]),
                self.debug)

    def app_can_be_rebalanced(self, application):
        try:
            data = {"energy":
                    {"structure":
                         {"energy":
                              {"usage": application["resources"]["energy"]["usage"],
                               "max": application["resources"]["energy"]["max"]}}},
                "cpu":
                    {"structure":
                         {"cpu":
                              {"usage": application["resources"]["cpu"]["usage"],
                               "min": application["resources"]["cpu"]["min"],
                               "current": application["resources"]["cpu"]["current"]}}}
                }
        except KeyError:
            return False

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
        global SHARE_SHUFFLING_AMOUNT
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
            SHARE_SHUFFLING_AMOUNT = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "SHARE_SHUFFLING_AMOUNT")

            # Get the applications and filter out the ones that do not need any rebalancing
            applications = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype="application")
            rebalanceable_apps = list()
            for app in applications:
                if self.app_can_be_rebalanced(app):
                    rebalanceable_apps.append(app)

            # Get the containers and applications
            containers = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype="container")

            # Sort them according to each application they belong
            app_containers = dict()
            for app in rebalanceable_apps:
                app_name = app["name"]
                app_containers_names = app["containers"]
                app_containers[app_name] = list()
                for container in containers:
                    if container["name"] in app_containers_names:
                        app_containers[app_name].append(container)
                # Get the container usages
                app_containers[app_name] = self.fill_containers_with_usage_info(app_containers[app_name], config)

            # Rebalance applications
            for app in rebalanceable_apps:
                app_name = app["name"]
                MyUtils.log_info("Going to rebalance {0} now".format(app_name), self.debug)
                self.rebalance_containers_by_pair_swapping(app_containers[app_name], app_name)

            MyUtils.log_info(
                "Epoch processed at {0}".format(MyUtils.get_time_now_string()), self.debug)
            time.sleep(window_difference)


def main():
    try:
        rebalancer = ReBalancer()
        rebalancer.rebalance()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

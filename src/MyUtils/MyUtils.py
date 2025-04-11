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

import random
import time
import logging
import sys
import requests
import traceback
from termcolor import colored

from src.MyUtils.metrics import RESOURCE_TO_BDW, RESOURCE_TO_SC, SC_TO_BDW, TAGS


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# DON'T NEED TO TEST
def resilient_beat(db_handler, service_name, max_tries=10):
    try:
        service = db_handler.get_service(service_name)
        service["heartbeat_human"] = time.strftime("%D %H:%M:%S", time.localtime())
        service["heartbeat"] = time.time()
        db_handler.update_service(service)
    except (requests.exceptions.HTTPError, ValueError) as e:
        if max_tries > 0:
            time.sleep((1000 + random.randint(1, 200)) / 1000)
            resilient_beat(db_handler, service_name, max_tries - 1)
        else:
            raise e


# DON'T NEED TO TEST
def beat(db_handler, service_name):
    resilient_beat(db_handler, service_name, max_tries=5)


class MyConfig:
    DEFAULTS_CONFIG = None
    config = None

    def __init__(self, DEFAULTS_CONFIG):
        self.DEFAULTS_CONFIG = DEFAULTS_CONFIG

    def get_config(self):
        return self.config

    def set_config(self, config):
        self.config = config

    def get_value(self, key):
        try:
            return self.config[key]
        except KeyError:
            return self.DEFAULTS_CONFIG[key]

    def set_value(self, key, value):
        self.config[key] = value


# DON'T NEED TO TEST
def get_config_value(config, default_config, key):
    try:
        return config[key]
    except KeyError:
        return default_config[key]


# Logging configuration
LOGGING_FORMAT = '[%(asctime)s]%(levelname)s:%(name)s:%(message)s'
LOGGING_DATEFMT = '%Y-%m-%d %H:%M:%S%z'


# DON'T NEED TO TEST
def debug_info(message, debug):
    if debug:
        print("[{0}] INFO: {1}".format(get_time_now_string(), message))


# DON'T NEED TO TEST
def log_info(message, debug):
    logging.info(message)
    debug_info(message, debug)


# DON'T NEED TO TEST
def log_warning(message, debug):
    logging.warning(message)
    if debug:
        print(colored("[{0}] WARN: {1}".format(get_time_now_string(), message), "yellow"))


# DON'T NEED TO TEST
def log_error(message, debug):
    logging.error(message)
    if debug:
        print(colored("[{0}] ERROR: {1}".format(get_time_now_string(), message), "red"))


# DON'T NEED TO TEST
def get_time_now_string():
    return str(time.strftime(LOGGING_DATEFMT, time.localtime()))


def get_host_containers(container_host_ip, container_host_port, rescaler_http_session, debug):
    try:
        full_address = "http://{0}:{1}/container/".format(container_host_ip, container_host_port)
        r = rescaler_http_session.get(full_address, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error(
            "Error trying to get container info {0} {1}".format(str(e), traceback.format_exc()),
            debug)
        return None


# CAN'T TEST
def get_container_resources(container, rescaler_http_session, debug):
    container_name = container["name"]
    try:
        container_host_ip = container["host_rescaler_ip"]
        container_host_port = container["host_rescaler_port"]

        full_address = "http://{0}:{1}/container/{2}".format(container_host_ip, container_host_port, container_name)
        r = rescaler_http_session.get(full_address, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error(
            "Error trying to get container {0} info {1} {2}".format(container_name, str(e), traceback.format_exc()),
            debug)
        return None


# CAN'T TEST
def register_service(db_handler, service):
    try:
        existing_service = db_handler.get_service(service["name"])
        # Service is registered, remove it
        db_handler.delete_service(existing_service)
    except ValueError:
        # Service is not registered, everything is fine
        pass
    db_handler.add_service(service)


# CAN'T TEST
def get_service(db_handler, service_name, max_allowed_failures=10, time_backoff_seconds=2):
    fails = 0
    success = False
    service = None
    # Get service info
    while not success:
        try:
            service = db_handler.get_service(service_name)
            success = True
        except (requests.exceptions.HTTPError, ValueError):
            # An error might have been thrown because database was recently updated or created
            # try again up to a maximum number of retries
            fails += 1
            if fails >= max_allowed_failures:
                message = "Fatal error, couldn't retrieve service."
                log_error(message, True)
                raise Exception(message)
            else:
                time.sleep(time_backoff_seconds)

    if not service or "config" not in service:
        message = "Fatal error, couldn't retrieve service configuration."
        log_error(message, True)
        raise Exception(message)

    return service


# TESTED
# Tranlsate something like '2-5,7' to [2,3,4,7]
def get_cpu_list(cpu_num_string):
    cpu_list = list()
    parts = cpu_num_string.split(",")
    for part in parts:
        ranges = part.split("-")
        if len(ranges) == 1:
            # Single core, no range (e.g., '5')
            cpu_list.append(ranges[0])
        else:
            # Range (e.g., '4-7' -> 4,5,6)
            cpu_list += range(int(ranges[0]), int(ranges[-1]) + 1)
    return [str(i) for i in cpu_list]


def copy_structure_base(structure):
    keys_to_copy = ["_id", "_rev", "type", "subtype", "name"]
    # TODO FIX, some structures types have specific fields, fix accordingly
    if structure["subtype"] == "container":
        keys_to_copy.append("host")
    new_struct = dict()
    for key in keys_to_copy:
        new_struct[key] = structure[key]
    return new_struct


def valid_resource(resource):
    if resource not in ["cpu", "mem", "disk", "disk_read", "disk_write", "net", "energy"]:
        return False
    else:
        return True

# DON'T NEED TO TEST
def get_resource(structure, resource):
    return structure["resources"][resource]


# CAN'T TEST
def update_structure(structure, db_handler, debug, max_tries=10):
    try:
        db_handler.update_structure(structure, max_tries=max_tries)
        log_info("{0} {1} ->  updated".format(structure["subtype"].capitalize(), structure["name"]), debug)
    except requests.exceptions.HTTPError:
        log_error("Error updating container " + structure["name"] + " " + traceback.format_exc(), debug)


def update_user(user, db_handler, debug, max_tries=10):
    try:
        db_handler.update_user(user, max_tries=max_tries)
        log_info("User {0} ->  updated".format(user["name"]), debug)
    except requests.exceptions.HTTPError:
        log_error("Error updating user " + user["name"] + " " + traceback.format_exc(), debug)


# CAN'T TEST
def get_structures(db_handler, debug, subtype="application"):
    try:
        return db_handler.get_structures(subtype=subtype)
    except (requests.exceptions.HTTPError, ValueError):
        log_warning("Couldn't retrieve " + subtype + " info.", debug=debug)
        return None


def start_epoch(debug):
    log_info("----------------------", debug)
    log_info("Starting Epoch", debug)
    return time.time()

def end_epoch(debug, window_difference, t0):
    t1 = time.time()
    time_proc = "%.2f" % (t1 - t0 - window_difference)
    time_total = "%.2f" % (t1 - t0)
    log_info("Epoch processed in {0} seconds ({1} processing and {2} sleeping)".format(time_total, time_proc, str(window_difference)), debug)
    log_info("----------------------\n", debug)


def wait_operation_thread(thread, debug):
    """This is used in services like the snapshoters or the Guardian that use threads to carry out operations.
    A main thread is launched that spawns the needed threads to carry out the operations. The service waits for this
    thread to finish.
    Args:
        thread (Python Thread): The thread that has spawned the basic threads that carry out operations as needed

    """
    if thread and thread.is_alive():
        log_warning("Previous thread didn't finish and next poll should start now", debug)
        log_warning("Going to wait until thread finishes before proceeding", debug)
        delay_start = time.time()
        thread.join()
        delay_end = time.time()
        log_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), debug)


# TESTED
def generate_request_name(amount, resource):
    if amount == 0:
        raise ValueError("Amount is zero")
    elif amount is None:
        raise ValueError("Amount is missing")
    if int(amount) < 0:
        return resource.title() + "RescaleDown"
    elif int(amount) > 0:
        return resource.title() + "RescaleUp"
    else:
        raise ValueError("Invalid amount")


def generate_request(structure, amount, resource_label, priority=0):
    action = generate_request_name(amount, resource_label)
    request = dict(
        type="request",
        resource=resource_label,
        amount=int(amount),
        priority=int(priority),
        structure=structure["name"],
        action=action,
        timestamp=int(time.time()),
        structure_type=structure["subtype"]
    )
    # For the moment, energy rescaling is uniquely mapped to cpu rescaling
    if resource_label == "energy":
        request["resource"] = "cpu"
        request["for_energy"] = True

    # If scaling a container, add its host information as it will be needed
    if structure_is_container(structure):
        request["host"] = structure["host"]
        request["host_rescaler_ip"] = structure["host_rescaler_ip"]
        request["host_rescaler_port"] = structure["host_rescaler_port"]

    return request


def structure_is_application(structure):
    return structure["subtype"] == "application"


def structure_is_container(structure):
    return structure["subtype"] == "container"


# TESTED
def generate_event_name(event, resource):
    if "scale" not in event:
        raise ValueError("Missing 'scale' key")

    if "up" not in event["scale"] and "down" not in event["scale"]:
        raise ValueError("Must have an 'up' or 'down count")

    elif "up" in event["scale"] and event["scale"]["up"] > 0 \
            and "down" in event["scale"] and event["scale"]["down"] > 0:
        # SPECIAL CASE OF HEAVY HYSTERESIS
        # raise ValueError("HYSTERESIS detected -> Can't have both up and down counts")
        if event["scale"]["up"] > event["scale"]["down"]:
            final_string = resource.title() + "Bottleneck"
        else:
            final_string = resource.title() + "Underuse"

    elif "down" in event["scale"] and event["scale"]["down"] > 0:
        final_string = resource.title() + "Underuse"

    elif "up" in event["scale"] and event["scale"]["up"] > 0:
        final_string = resource.title() + "Bottleneck"
    else:
        raise ValueError("Error generating event name")

    return final_string


def generate_structure_usage_metric(resource):
    return "structure.{0}.usage".format(resource)


def get_tag(structure_subtype):
    return TAGS.get(structure_subtype, None)


def structure_subtype_is_supported(structure_subtype):
    return (structure_subtype in RESOURCE_TO_BDW and structure_subtype in RESOURCE_TO_SC
            and structure_subtype in SC_TO_BDW and structure_subtype in TAGS)


def get_metrics_to_retrieve_and_generate(resources, structure_subtype):
    """Maps resources (e.g., cpu, mem) to the metrics that need to be retrieved from BDWatchdog (e.g., proc.cpu.user,
    proc.mem.resident) and the metrics that need to be generated (e.g., structure.cpu.usage, structure.mem.usage)

    Args:
        resources (list): List of resources to map
        structure_subtype (str): Type of structure (e.g., container, application)

    Returns:
        tuple: Tuple containing the list of metrics to retrieve and a dictionary mapping the metrics to generate

    Example:

        Running:
            get_metrics_to_retrieve_and_generate(["cpu", "disk"], "container")

        Returns:
            metrics_to_retrieve = ['proc.cpu.user', 'proc.cpu.kernel', 'proc.disk.reads.mb', 'proc.disk.writes.mb'],
            metrics_to_generate = {
                'structure.cpu.usage': ['proc.cpu.user', 'proc.cpu.kernel'],
                'structure.cpu.user': ['proc.cpu.user'],
                'structure.cpu.kernel': ['proc.cpu.kernel'],
                'structure.disk.usage': ['proc.disk.reads.mb', 'proc.disk.writes.mb']
                }
    """

    def get_mapping(d, subtype, key=None):
        return d.get(subtype, {}).get(key, []) if key else d.get(subtype, {})

    metrics_to_retrieve = list()
    metrics_to_generate = dict()
    for res in resources:
        metrics_to_retrieve += get_mapping(RESOURCE_TO_BDW, structure_subtype, res)
        for usage_metric in get_mapping(RESOURCE_TO_SC, structure_subtype, res):
            metrics_to_generate[usage_metric] = get_mapping(SC_TO_BDW, structure_subtype, usage_metric)

    return metrics_to_retrieve, metrics_to_generate


def get_container_usages(resources, container, window_difference, window_delay, opentsdb_handler, debug):
    structure_subtype = "container"
    metrics_to_retrieve, metrics_to_generate = get_metrics_to_retrieve_and_generate(resources, "container")
    tag = get_tag(structure_subtype)

    try:
        # Remote database operation
        usages = opentsdb_handler.get_structure_timeseries({tag: container["name"]},
                                                           window_difference,
                                                           window_delay,
                                                           metrics_to_retrieve,
                                                           metrics_to_generate)

        # Skip this structure if all the usage metrics are unavailable
        if all([usages[metric] == opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
            log_warning("container: {0} has no usage data".format(container["name"]), debug)
            return None

        return usages
    except Exception as e:
        log_error("error with structure: {0} {1} {2}".format(container["name"],
                                                             str(e), str(traceback.format_exc())), debug)

    return None

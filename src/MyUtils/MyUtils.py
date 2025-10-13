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
import os
import yaml
import json
import requests
import traceback
from termcolor import colored
from threading import Thread

from src.MyUtils.metrics import RESOURCE_TO_BDW, RESOURCE_TO_SC, SC_TO_BDW, TAGS, TRANSLATOR_DICT

VALID_RESOURCES = {"cpu", "mem", "disk", "disk_read", "disk_write", "net", "energy"}

# Logging configuration
LOGGING_FORMAT = '[%(asctime)s]%(levelname)s:%(name)s:%(message)s'
LOGGING_DATEFMT = '%Y-%m-%d %H:%M:%S%z'

class MyConfig:

    _config = None

    def __init__(self, config):
        self._config = config.copy()

    def get_config(self):
        return self._config

    def set_config(self, config):
        self._config.update(config)

    def get_value(self, key):
        return self._config.get(key, None)

    def set_value(self, key, value):
        self._config[key] = value


# DON'T NEED TO TEST
def get_config_value(config, default_config, key):
    try:
        return config[key]
    except KeyError:
        return default_config[key]


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


def get_orchestrator_url():
    serverless_path = os.environ['SERVERLESS_PATH']
    with open(serverless_path + "/services_config.yml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return "http://{0}:{1}".format(config['ORCHESTRATOR_URL'], config['ORCHESTRATOR_PORT'])


def put_request_to_orchestrator(url, error_message, headers, data):
    response = requests.put(url, data=json.dumps(data), headers=headers)
    error = ""
    if response != "" and not response.ok:
        error = "{0}: {1}".format(error_message, response.text.strip())

    return error, response


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
    return resource in VALID_RESOURCES


# DON'T NEED TO TEST
def get_resource(structure, resource):
    return structure["resources"][resource]


# CAN'T TEST
def update_resource_in_couchdb(structure, resource, field, value, db_handler, debug, max_tries=3, backoff_time_ms=500):
    old_value = structure["resources"][resource][field]
    amount_scaled = value - structure["resources"][resource][field]
    put_done, tries = False, 0
    while not put_done:
        if tries >= max_tries:
            log_error("Could not update {0} '{1}' value for structure {2} for {3} tries, aborting"
                      .format(resource, field, structure["name"], max_tries), debug)
            return

        structure["resources"][resource][field] = value
        persist_data(structure, db_handler, debug)

        time.sleep(backoff_time_ms / 1000)

        if structure_is_user(structure):
            structure = db_handler.get_user(structure["name"])
        else:
            structure = db_handler.get_structure(structure["name"])
        put_done = structure["resources"][resource][field] == value

        tries += 1

    log_info("Resource {0} value for structure {1} has been updated from {2} to {3}".format(resource, structure["name"], old_value, value), debug)

    # If "current" is being updated, host "free" resources must also be updated
    if structure["subtype"] == "container" and field == "current":
        put_done, tries = False, 0
        host = db_handler.get_structure(structure["host"])
        new_host_free = host["resources"][resource]["free"] - amount_scaled
        while not put_done:
            if tries >= max_tries:
                log_error("Could not update free {0} value for host {1} for {2} tries, aborting"
                          .format(resource, host["name"], max_tries), debug)
                return

            host["resources"][resource]["free"] = new_host_free
            db_handler.update_structure(host)

            time.sleep(backoff_time_ms / 1000)

            host = db_handler.get_structure(structure["host"])
            put_done = host["resources"][resource]["free"] == new_host_free

            tries += 1

        log_info("Host {0} free {1} has been updated according to structure {2} scaling ({3})".format(structure["host"], resource, structure["name"], amount_scaled), debug)


def update_structure(structure, db_handler, debug, max_tries=10):
    try:
        db_handler.update_structure(structure, max_tries=max_tries)
        log_info("{0} {1} ->  updated".format(structure["subtype"].capitalize(), structure["name"]), debug)
    except requests.exceptions.HTTPError:
        log_error("Error updating {0} {1}: {2} ".format(structure["subtype"].capitalize(), structure["name"], traceback.format_exc()), debug)


def update_user(user, db_handler, debug, max_tries=10):
    try:
        db_handler.update_user(user, max_tries=max_tries)
        log_info("User {0} ->  updated".format(user["name"]), debug)
    except requests.exceptions.HTTPError:
        log_error("Error updating user {0}: {1} ".format(user["name"], traceback.format_exc()), debug)


def persist_data(data, db_handler, debug):
    if data["type"] == "user" or data["subtype"] == "user":
        update_user(data, db_handler, debug)  # Remote database operation
    elif data["type"] == "structure":
        update_structure(data, db_handler, debug)  # Remote database operation
    else:
        log_error("Trying to persist unknown data type '{0}'".format(data["type"]), debug)


# CAN'T TEST
def get_structures(db_handler, debug, subtype="application"):
    try:
        return db_handler.get_structures(subtype=subtype)
    except (requests.exceptions.HTTPError, ValueError):
        log_warning("Couldn't retrieve " + subtype + " info.", debug=debug)
        return None


def get_users(db_handler, debug):
    try:
        return db_handler.get_users()
    except (requests.exceptions.HTTPError, ValueError):
        log_warning("Couldn't retrieve users info.", debug=debug)
        return None


def run_in_threads(structures, worker_fn, *worker_args):
    threads = []
    for structure in structures:
        process = Thread(target=worker_fn, args=(structure, *worker_args))
        process.start()
        threads.append(process)

    for process in threads:
        process.join()


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


def structure_is_user(structure):
    return structure["subtype"] == "user" or structure["type"] == "user"


def structure_is_application(structure):
    return structure["subtype"] == "application"


def structure_is_container(structure):
    return structure["subtype"] == "container"


# TESTED
def generate_event_name(event, resource):
    if "scale" not in event:
        raise ValueError("Missing 'scale' key")

    up = event["scale"].get("up", 0)
    down = event["scale"].get("down", 0)

    if up <= 0 and down <= 0:
        raise ValueError("Must have an 'up' or 'down' count with positive values")

    if up > 0 and down > 0:
        # Hysteresis
        return resource.title() + ("Bottleneck" if up > down else "Underuse")

    return resource.title() + ("Bottleneck" if up > 0 else "Underuse")


def generate_structure_usage_metric(resource):
    return "structure.{0}.usage".format(resource)


def get_tag(structure_subtype):
    return TAGS.get(structure_subtype, None)


def res_to_metric(res):
    return TRANSLATOR_DICT.get(res, None)


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


def get_structure_usages(resources, structure, window_difference, window_delay, opentsdb_handler, debug):
    metrics_to_retrieve, metrics_to_generate = get_metrics_to_retrieve_and_generate(resources, structure["subtype"])
    tag = get_tag(structure["subtype"])

    usages = dict()

    try:
        # Remote database operation
        usages = opentsdb_handler.get_structure_timeseries({tag: structure["name"]},
                                                           window_difference,
                                                           window_delay,
                                                           metrics_to_retrieve,
                                                           metrics_to_generate)

        # Skip this structure if all the usage metrics are unavailable
        if all([usages[metric] == opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE for metric in usages]):
            log_warning("structure: {0} has no usage data".format(structure["name"]), debug)
            return dict()

    except Exception as e:
        log_error("error with structure: {0} {1} {2}".format(structure["name"],
                                                             str(e), str(traceback.format_exc())), debug)

    return usages


def host_info_request(host, container_info, valid_containers, rescaler_http_session, debug):
    host_containers = get_host_containers(host["host_rescaler_ip"], host["host_rescaler_port"], rescaler_http_session, debug)
    for container_name in host_containers:
        if container_name in valid_containers:
            container_info[container_name] = host_containers[container_name]


def fill_container_dict(hosts_info, containers, rescaler_http_session, debug):
    container_info = {}
    threads = []
    valid_containers = [c["name"] for c in containers]
    for hostname in hosts_info:
        host = hosts_info[hostname]
        t = Thread(target=host_info_request, args=(host, container_info, valid_containers, rescaler_http_session, debug))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return container_info


def get_container_resources_dict(containers, rescaler_http_session, debug):
    if not containers:
        return {}

    # Get all the different hosts of the containers
    hosts_info = {}
    for container in containers:
        host = container["host"]
        if host not in hosts_info:
            hosts_info[host] = {}
            hosts_info[host]["host_rescaler_ip"] = container["host_rescaler_ip"]
            hosts_info[host]["host_rescaler_port"] = container["host_rescaler_port"]

    # Retrieve all the containers on the host and persist the ones that we look for
    container_info = fill_container_dict(hosts_info, containers, rescaler_http_session, debug)
    container_resources_dict = {}
    for container in containers:
        container_name = container["name"]
        if container_name not in container_info:
            log_warning("Container info for {0} not found, check that it is really living in its supposed "
                        "host '{1}', and that the host is alive and with the Node Scaler service running"
                        .format(container_name, container["host"]), debug)
            continue
        # Manually add energy limit as there is no physical limit that can be obtained from NodeRescaler
        if "energy" in container["resources"]:
            container_info[container_name]["energy"] = {"energy_limit": container["resources"]["energy"]["current"]}
        container_resources_dict[container_name] = dict(container)
        container_resources_dict[container_name]["resources"] = container_info[container_name]

    return container_resources_dict

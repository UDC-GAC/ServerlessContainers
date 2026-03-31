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

from src.MyUtils.metrics import RESOURCE_TO_BDW, RESOURCE_TO_SC, SC_TO_BDW, TAGS, TRANSLATOR_DICT, VALID_RESOURCES


######################################################################################################
# SERVICES CONFIGURATION
######################################################################################################
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


######################################################################################################
# SERVICES LOGGING
######################################################################################################
LOGGING_FORMAT = '[%(asctime)s]%(levelname)s:%(name)s:%(message)s'
LOGGING_DATEFMT = '%Y-%m-%d %H:%M:%S%z'


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def log_info(message, debug):
    logging.info(message)
    debug_info(message, debug)


def log_warning(message, debug):
    logging.warning(message)
    if debug:
        print(colored("[{0}] WARN: {1}".format(get_time_now_string(), message), "yellow"))


def log_error(message, debug):
    logging.error(message)
    if debug:
        print(colored("[{0}] ERROR: {1}".format(get_time_now_string(), message), "red"))


def debug_info(message, debug):
    if debug:
        print("[{0}] INFO: {1}".format(get_time_now_string(), message))


def get_time_now_string():
    return str(time.strftime(LOGGING_DATEFMT, time.localtime()))


######################################################################################################
# COUCHDB
######################################################################################################
# --------------------------------------        Heartbeat       --------------------------------------
def resilient_beat(db_handler, service_name, max_tries=10):
    try:
        service = db_handler.get_service(service_name)
        service["heartbeat_human"] = time.strftime("%D %H:%M:%S", time.localtime())
        service["heartbeat"] = time.time()
        db_handler.partial_update_service(service, {"heartbeat_human": service["heartbeat_human"], "heartbeat": service["heartbeat"]})
    except (requests.exceptions.HTTPError, ValueError) as e:
        if max_tries > 0:
            time.sleep((1000 + random.randint(1, 200)) / 1000)
            resilient_beat(db_handler, service_name, max_tries - 1)
        else:
            raise e


# DON'T NEED TO TEST
def beat(db_handler, service_name):
    resilient_beat(db_handler, service_name, max_tries=5)


# --------------------------------------        Services        --------------------------------------
def register_service(db_handler, service):
    try:
        existing_service = db_handler.get_service(service["name"])
        # Service is registered, remove it
        db_handler.delete_service(existing_service)
    except ValueError:
        # Service is not registered, everything is fine
        pass
    db_handler.add_service(service)


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


# --------------------------------------       Structures       --------------------------------------
def structure_is(structure, subtypes):
    return structure["subtype"] in subtypes


def update_structure(structure, db_handler, debug, partial=False, changes=None, max_tries=10):
    partial_str = " partially" if partial else ""
    try:
        if structure_is(structure, {"user"}):
            if partial:
                db_handler.partial_update_user(structure, changes, max_tries=max_tries)
            else:
                db_handler.update_user(structure, max_tries=max_tries)
        elif structure_is(structure, {"container", "application", "host"}):
            if partial:
                db_handler.partial_update_structure(structure, changes, max_tries=max_tries)
            else:
                db_handler.update_structure(structure, max_tries=max_tries)
        else:
            log_error("Trying to persist unknown data type '{0} ({1})'".format(structure["type"], structure["subtype"]), debug)
            return

        log_info("{0} {1} ->{2} updated".format(structure["subtype"].capitalize(), structure['name'], partial_str), debug)

    except requests.exceptions.HTTPError:
        log_error("Error{0} updating {1} {2}: {3}".format(partial_str, structure["subtype"].capitalize(), structure['name'], traceback.format_exc()), debug)


def update_resource_in_couchdb(structure, resource, field, value, db_handler, debug, max_tries=3, backoff_time_ms=500):
    old_value = structure["resources"][resource][field]
    changes = {"resources": {resource: {field: value}}}
    put_done, tries = False, 0
    while not put_done:
        if tries >= max_tries:
            log_error("Could not update {0} '{1}' value for structure {2} for {3} tries, aborting"
                      .format(resource, field, structure["name"], max_tries), debug)
            return

        # Set structure resource value and update in CouchDB
        structure["resources"][resource][field] = value
        update_structure(structure, db_handler, debug, partial=True, changes=changes)
        time.sleep(backoff_time_ms / 1000)

        # Check structure has been successfully updated
        structure = get_structures(db_handler, debug, structure["subtype"], structure["name"])
        put_done = structure["resources"][resource][field] == value
        tries += 1

    log_info("Resource {0} value for structure {1} has been updated from {2} to {3}".format(resource, structure["name"], old_value, value), debug)


def get_structures(db_handler, debug, subtype, structure_name=None):
    structure_msg = " for '{0}'".format(structure_name) if structure_name else ""
    try:
        if subtype == "user":
            if structure_name:
                return db_handler.get_user(structure_name)
            return db_handler.get_users()
        elif subtype in {"container", "application", "host"}:
            if structure_name:
                return db_handler.get_structure(structure_name)
            return db_handler.get_structures(subtype=subtype)
        else:
            log_warning("Trying to get unknown data type '{0}'{1}".format(subtype, structure_msg), debug)
    except (requests.exceptions.HTTPError, ValueError):
        log_warning("Couldn't retrieve {0} info{1}".format(subtype, structure_msg), debug=debug)
    return None


# --------------------------------------        Requests        --------------------------------------
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


def generate_request(structure, amount, resource_label, priority=0, field="current"):
    action = generate_request_name(amount, resource_label)
    request = dict(
        type="request",
        resource=resource_label,
        amount=int(amount),
        priority=int(priority),
        structure=structure["name"],
        action=action,
        field=field,
        timestamp=int(time.time()),
        structure_type=structure["subtype"]
    )

    # If scaling a container, add its host information as it will be needed
    if structure_is(structure, {"container"}):
        request["host"] = structure["host"]
        request["host_rescaler_ip"] = structure["host_rescaler_ip"]
        request["host_rescaler_port"] = structure["host_rescaler_port"]

    return request


# --------------------------------------         Events         --------------------------------------
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


######################################################################################################
# ORCHESTRATOR
######################################################################################################
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


######################################################################################################
# PROPAGATION/REBALANCING LOGIC
######################################################################################################
def get_best_fit_container(scalable_containers, resource, amount, field):
    best_fit_container, normal_containers, below_min_containers = {}, [], []
    for container in scalable_containers:
        if container["resources"][resource][field] < container["resources"][resource]["min"]:
            below_min_containers.append(container)
        else:
            normal_containers.append(container)
    sorted_containers = sorted(below_min_containers, key=lambda c: c["resources"][resource]["max"] / c["resources"][resource]["min"])
    sorted_containers += sorted(normal_containers, key=lambda c: c["resources"][resource][field] - c["resources"][resource]["usage"])
    if sorted_containers:
        best_fit_container = sorted_containers[0] if amount > 0 else sorted_containers[-1]

    return best_fit_container


def get_best_fit_app(scalable_apps, resource, amount):
    stopped_apps, below_min_apps, running_apps = [], [], []
    for app in scalable_apps:
        if "usage" not in app["resources"][resource]:
            continue
        if app["resources"][resource].get("current", 0) == 0 and not app.get("running", False):
            stopped_apps.append(app)
        else:
            if app["resources"][resource]["max"] < app["resources"][resource]["min"]:
                below_min_apps.append(app)
            else:
                running_apps.append(app)
    # When scaling down, stopped apps are preferred, when scaling up, apps below min are prioritised and then running apps are preferred
    sorted_apps = sorted(below_min_apps, key=lambda a: a["resources"][resource]["max"] / a["resources"][resource]["min"])
    sorted_apps += sorted(running_apps, key=lambda a: a["resources"][resource]["max"] - a["resources"][resource]["usage"])
    sorted_apps += sorted(stopped_apps, key=lambda a: a["resources"][resource]["max"])

    return sorted_apps[0] if amount > 0 else sorted_apps[-1]


######################################################################################################
# NODE RESCALER
######################################################################################################
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


def query_node_rescaler(rescaler_session, address, params, debug):
    try:
        r = rescaler_session.get(address, params=params, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return dict(r.json())
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error("Error trying to get containers info {0} {1}".format(str(e), traceback.format_exc()), debug)
        return None


def get_single_container_info_from_rescaler(container_host_ip, container_host_port, container_name, needed_resources, rescaler_session, debug):
    params = {resource: 1 for resource in needed_resources}
    full_address = "http://{0}:{1}/container/resources/{2}".format(container_host_ip, container_host_port, container_name)
    return query_node_rescaler(rescaler_session, full_address, params, debug)


def get_containers_info_from_rescaler(container_host_ip, container_host_port, needed_resources, rescaler_session, debug):
    params = {resource: 1 for resource in needed_resources}
    full_address = "http://{0}:{1}/container/resources/".format(container_host_ip, container_host_port)
    return query_node_rescaler(rescaler_session, full_address, params, debug)


def fill_container_dict(hosts_targets, needed_resources, rescaler_session, debug):
    def _req(_ip, _port, _resources, _info, _valid, _session, _debug):
        if len(_valid) == 1:
            cont_name = next(iter(_valid))
            host_containers = {cont_name: get_single_container_info_from_rescaler(_ip, _port, next(iter(_valid)), _resources, _session, _debug)}
        else:
            host_containers = get_containers_info_from_rescaler(_ip, _port, _resources, _session, _debug)
        for cont_name in host_containers:
            if cont_name in _valid:
                _info[cont_name] = host_containers[cont_name]

    threads, container_info = [], {}
    for (host_ip, host_port), valid_containers in hosts_targets.items():
        t = Thread(target=_req, args=(host_ip, host_port, needed_resources, container_info, valid_containers, rescaler_session, debug))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return container_info


def get_container_physical_resources(containers, needed_resources, rescaler_session, debug):
    if not containers:
        return {}

    hosts_targets = {}
    for c in containers:
        host_key = (c["host_rescaler_ip"], c["host_rescaler_port"])
        hosts_targets.setdefault(host_key, set()).add(c["name"])

    # Retrieve all the containers on the host and persist the ones that we look for
    container_info = fill_container_dict(hosts_targets, needed_resources, rescaler_session, debug)
    cont_phy_resources = {}
    for container in containers:
        container_name = container["name"]
        if container_name not in container_info:
            raise Exception("Container info for {0} not found, check that it is really living in its supposed "
                            "host '{1}', and that the host is alive and with the Node Scaler service running"
                            .format(container_name, container["host"]), debug)
        # Until energy limit is virtually initialised through NodeRescaler, the value from StateDatabase is used
        if "energy" in container["resources"] and "energy_limit" not in container_info[container_name].get("energy", {}):
            container_info[container_name]["energy"] = {"energy_limit": container["resources"]["energy"]["current"]}
        cont_phy_resources[container_name] = dict(container)
        cont_phy_resources[container_name]["resources"] = container_info[container_name]

    return cont_phy_resources


def set_container_physical_resources(rescaler_session, container, resources, debug):
    rescaler_ip = container["host_rescaler_ip"]
    rescaler_port = container["host_rescaler_port"]
    container_name = container["name"]
    r = rescaler_session.put("http://{0}:{1}/container/{2}".format(rescaler_ip, rescaler_port, container_name),
                             data=json.dumps(resources), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    if r.status_code == 201:
        return dict(r.json())
    else:
        log_error("Error processing container resource change in host in IP {0}".format(rescaler_ip), debug)
        log_error(str(json.dumps(r.json())), debug)
        r.raise_for_status()


######################################################################################################
# BDWATCHDOG
######################################################################################################
def get_tag(structure_subtype):
    return TAGS.get(structure_subtype, None)


def res_to_metric(res):
    return TRANSLATOR_DICT.get(res, None)


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

    metrics_to_retrieve, metrics_to_generate = [], {}
    for res in resources:
        metrics_to_retrieve += get_mapping(RESOURCE_TO_BDW, structure_subtype, res)
        for usage_metric in get_mapping(RESOURCE_TO_SC, structure_subtype, res):
            metrics_to_generate[usage_metric] = get_mapping(SC_TO_BDW, structure_subtype, usage_metric)

    return metrics_to_retrieve, metrics_to_generate


def get_structure_usages(resources, structure, window_difference, window_delay, opentsdb_handler, debug):
    metrics_to_retrieve, metrics_to_generate = get_metrics_to_retrieve_and_generate(resources, structure["subtype"])
    tag = get_tag(structure["subtype"])

    usages = {}
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


######################################################################################################
# GENERAL UTILITIES
######################################################################################################
def valid_resource(resource):
    return resource in VALID_RESOURCES


def structure_subtype_is_supported(structure_subtype):
    return (structure_subtype in RESOURCE_TO_BDW and structure_subtype in RESOURCE_TO_SC
            and structure_subtype in SC_TO_BDW and structure_subtype in TAGS)


def split_amount_in_slices(total_amount, slice_amount):
    number_of_slices = int(total_amount // slice_amount)
    last_slice_amount = total_amount % slice_amount
    return [slice_amount] * number_of_slices + ([last_slice_amount] if abs(last_slice_amount) > 0 else [])


def split_amount_in_num_slices(total_amount, number_of_slices):
    slice_amount = int(total_amount // number_of_slices)
    last_slice_amount = total_amount % number_of_slices
    if slice_amount == 0:
        return [last_slice_amount]
    return [slice_amount + last_slice_amount] + [slice_amount] * (number_of_slices - 1)


def get_cpu_list(cpu_num_string):
    """ Translates something like '2-5,7' to [2,3,4,7] """
    cpu_list = list()
    parts = cpu_num_string.split(",")
    for part in parts:
        ranges = part.split("-")
        if len(ranges) == 1:
            cpu_list.append(ranges[0])  # Single core, no range (e.g., '5')
        else:
            cpu_list += range(int(ranges[0]), int(ranges[-1]) + 1)  # Range (e.g., '4-7' -> 4,5,6)
    return [str(i) for i in cpu_list]


def run_in_threads(structures, worker_fn, *worker_args):
    threads = []
    for structure in structures:
        process = Thread(target=worker_fn, args=(structure, *worker_args))
        process.start()
        threads.append(process)

    for process in threads:
        process.join()

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


from __future__ import print_function

from threading import Thread
import requests
import json
import time
import traceback
import logging

import src.StateDatabase.couchdb as couchDB
from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, \
    update_structure, get_host_containers, get_structures, copy_structure_base, wait_operation_thread, log_warning

db_handler = couchDB.CouchDBServer()
rescaler_http_session = requests.Session()
translate_map = {
    "cpu": {"metric": "structure.cpu.current", "limit_label": "effective_cpu_limit"},
    "mem": {"metric": "structure.mem.current", "limit_label": "mem_limit"},
    "disk": {"metric": "structure.disk.current", "limit_label": "disk_read_limit"},  # FIXME missing write value
    "net": {"metric": "structure.net.current", "limit_label": "net_limit"}
}
SERVICE_NAME = "structures_snapshoter"
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "DEBUG": True, "PERSIST_APPS": True, "RESOURCES_PERSISTED": ["cpu"], "ACTIVE": True}
MAX_FAIL_NUM = 5
debug = True
resources_persisted = ["cpu"]


def generate_timeseries(container_name, resources):
    timestamp = int(time.time())

    for resource in resources_persisted:
        value = resources[resource][translate_map[resource]["limit_label"]]
        metric = translate_map[resource]["metric"]
        timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=container_name))

        print(json.dumps(timeseries))


def update_container_current_values(container_name, resources):
    if not resources:
        log_error("Unable to get resource info for container {0}".format(container_name), debug)

    # Remote database operation
    database_structure = db_handler.get_structure(container_name)
    new_structure = copy_structure_base(database_structure)
    new_structure["resources"] = dict()
    for resource in resources_persisted:
        if resource not in new_structure:
            new_structure["resources"][resource] = dict()

        if resource not in resources or not resources[resource]:
            log_error("Unable to get info for resource {0} for container {1}".format(resource, container_name), debug)
            new_structure["resources"][resource]["current"] = 0
        else:
            new_structure["resources"][resource]["current"] = resources[resource][translate_map[resource]["limit_label"]]

    # Remote database operation
    update_structure(new_structure, db_handler, debug, max_tries=3)


def thread_persist_container(container, container_resources_dict):
    container_name = container["name"]

    # Try to get the container resources, if unavailable, continue with others
    # Remote operation
    # resources = MyUtils.get_container_resources(container, rescaler_http_session, debug)
    resources = container_resources_dict[container_name]["resources"]
    if not resources:
        log_error("Couldn't get container's {0} resources".format(container_name), debug)
        return

    # Persist by updating the Database current value
    update_container_current_values(container_name, resources)


def persist_containers(container_resources_dict):
    # Try to get the containers, if unavailable, return
    # Remote database operation
    containers = get_structures(db_handler, debug, subtype="container")
    if not containers:
        return

    # Retrieve each container resources, persist them and store them to generate host info
    threads = []
    for container in containers:
        # Check that the document has been properly initialized, otherwise it might be overwritten with just
        # the "current" value without possibility of correcting it
        if "cpu" not in container["resources"] or "max" not in container["resources"]["cpu"]:
            continue

        process = Thread(target=thread_persist_container, args=(container, container_resources_dict,))
        process.start()
        threads.append(process)

    for process in threads:
        process.join()


def persist_applications(container_resources_dict):
    # Try to get the applications, if unavailable, return
    # Remote database operation
    applications = get_structures(db_handler, debug, subtype="application")
    if not applications:
        return

    # Generate the applications current resource values
    for app in applications:
        for resource in resources_persisted:
            if resource not in app["resources"]:
                log_error("Application {0} is missing info of resource {1}".format(app["name"], resource), debug)
            else:
                app["resources"][resource]["current"] = 0

        application_containers = app["containers"]
        for container_name in application_containers:

            if container_name not in container_resources_dict:
                log_error(
                    "Container info {0} is missing for app : {1}".format(container_name, app["name"])
                    + " app info will not be totally accurate", debug)
                continue

            for resource in resources_persisted:
                try:
                    current_resource_label = translate_map[resource]["limit_label"]
                    container_resources = container_resources_dict[container_name]["resources"]

                    if resource not in container_resources or not container_resources[resource]:
                        log_error(
                            "Unable to get info for resource {0} for container {1} when computing {2} resources".format(
                                resource, container_name, app["name"]), debug)
                    else:
                        app["resources"][resource]["current"] += container_resources[resource][current_resource_label]
                except KeyError:
                    if "name" in container_resources_dict[container_name] and "name" in app:
                        log_error(
                            "Container info {0} is missing for app : {1} and resource {2} resource,".format(
                                container_name, app["name"], resource)
                            + " app info will not be totally accurate", debug)
                    else:
                        log_error("Error with app or container info", debug)
                        # TODO this error should be more self-explanatory

        # Remote database operation
        update_structure(app, db_handler, debug)


def fill_container_dict(hosts_info, containers):
    def host_info_request(h, d):
        host_containers = get_host_containers(h["host_rescaler_ip"], h["host_rescaler_port"], rescaler_http_session, debug)
        for container_name in host_containers:
            if container_name in container_list_names:
                d[container_name] = host_containers[container_name]

    container_list_names = [c["name"] for c in containers]
    container_info = dict()
    threads = list()
    for hostname in hosts_info:
        host = hosts_info[hostname]
        t = Thread(target=host_info_request, args=(host, container_info,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return container_info


def get_container_resources_dict():
    # Remote database operation
    containers = get_structures(db_handler, debug, subtype="container")
    if not containers:
        return

    # Get all the different hosts of the containers
    hosts_info = dict()
    for container in containers:
        cont_host = container["host"]
        if cont_host not in hosts_info:
            hosts_info[cont_host] = dict()
            hosts_info[cont_host]["host_rescaler_ip"] = container["host_rescaler_ip"]
            hosts_info[cont_host]["host_rescaler_port"] = container["host_rescaler_port"]

    # For each host, retrieve its containers and persist the ones we look for
    container_info = fill_container_dict(hosts_info, containers)

    container_resources_dict = dict()
    for container in containers:
        container_name = container["name"]
        container_resources_dict[container_name] = container
        container_resources_dict[container_name]["resources"] = container_info[container_name]

    return container_resources_dict


def persist_thread():
    t0 = time.time()
    container_resources_dict = get_container_resources_dict()
    t1 = time.time()
    persist_applications(container_resources_dict)
    t2 = time.time()
    persist_containers(container_resources_dict)
    t3 = time.time()

    log_info("It took {0} seconds to get container info".format(str("%.2f" % (t1 - t0))), debug)
    log_info("It took {0} seconds to snapshot applications".format(str("%.2f" % (t2 - t1))), debug)
    log_info("It took {0} seconds to snapshot containers".format(str("%.2f" % (t3 - t2))), debug)

def invalid_conf(config):
    # TODO THis code is duplicated on the structures and database snapshoters
    for key, num in [("POLLING_FREQUENCY",config.get_value("POLLING_FREQUENCY"))]:
        if num < 3:
            return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
    return False, ""

def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

    global resources_persisted
    global debug

    myConfig = MyConfig(CONFIG_DEFAULT_VALUES)

    while True:
        log_info("----------------------", debug)
        log_info("Starting Epoch", debug)
        t0 = time.time()

        # Get service info
        service = get_service(db_handler, SERVICE_NAME)  # Remote database operation

        # Heartbeat
        beat(db_handler, SERVICE_NAME)  # Remote database operation

        # CONFIG
        myConfig.set_config(service["config"])
        polling_frequency = myConfig.get_value("POLLING_FREQUENCY")
        debug = myConfig.get_value("DEBUG")
        resources_persisted = myConfig.get_value("RESOURCES_PERSISTED")
        SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")
        log_info("Going to snapshot resources: {0}".format(resources_persisted), debug)

        log_info("Config is as follows:", debug)
        log_info(".............................................", debug)
        log_info("Polling frequency -> {0}".format(polling_frequency), debug)
        log_info("Resources to be snapshoter are -> {0}".format(resources_persisted), debug)
        log_info(".............................................", debug)

        ## CHECK INVALID CONFIG ##
        # TODO THis code is duplicated on the structures and database snapshoters
        invalid, message = invalid_conf(myConfig)
        if invalid:
            log_error(message, debug)
            time.sleep(polling_frequency)
            if polling_frequency < 5:
                log_error("Polling frequency is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]), debug)
                polling_frequency = CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]

            log_info("----------------------\n", debug)
            time.sleep(polling_frequency)
            continue

        thread = None
        if SERVICE_IS_ACTIVATED:
            thread = Thread(target=persist_thread, args=())
            thread.start()
        else:
            log_warning("Structure snapshoter is not activated, will not do anything", debug)

        time.sleep(polling_frequency)

        wait_operation_thread(thread, debug)

        t1 = time.time()
        time_proc = "%.2f" % (t1 - t0 - polling_frequency)
        time_total = "%.2f" % (t1 - t0)
        log_info("Epoch processed in {0} seconds ({1} processing and {2} sleeping)".format(time_total, time_proc, str(polling_frequency)), debug)
        log_info("----------------------\n", debug)


def main():
    try:
        persist()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

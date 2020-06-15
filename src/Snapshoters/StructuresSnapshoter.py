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
from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    get_time_now_string, update_structure, get_host_containers, get_structures, copy_structure_base

db_handler = couchDB.CouchDBServer()
rescaler_http_session = requests.Session()
RESOURCES = ["cpu", "mem"]
translate_map = {
    "cpu": {"metric": "structure.cpu.current", "limit_label": "effective_cpu_limit"},
    "mem": {"metric": "structure.mem.current", "limit_label": "mem_limit"},
    "disk": {"metric": "structure.disk.current", "limit_label": "disk_read_limit"},  # FIXME missing write value
    "net": {"metric": "structure.net.current", "limit_label": "net_limit"}
}
SERVICE_NAME = "structures_snapshoter"
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True, "PERSIST_APPS": True, "ACTIVE": True}
MAX_FAIL_NUM = 5
debug = True


def generate_timeseries(container_name, resources):
    timestamp = int(time.time())

    for resource in RESOURCES:
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
    for resource in RESOURCES:
        if resource not in new_structure:
            new_structure["resources"][resource] = dict()

        if resource not in resources or not resources[resource]:
            log_error("Unable to get info for resource {0} for container {1}".format(resource, container_name),
                      debug)
            new_structure["resources"][resource]["current"] = 0
        else:
            new_structure["resources"][resource]["current"] = resources[resource][
                translate_map[resource]["limit_label"]]

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
        for resource in RESOURCES:
            app["resources"][resource]["current"] = 0

        application_containers = app["containers"]
        for container_name in application_containers:

            if container_name not in container_resources_dict:
                log_error(
                    "Container info {0} is missing for app : {1}".format(container_name, app["name"])
                    + " app info will not be totally accurate", debug)
                continue

            for resource in RESOURCES:
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


def fill_container_dict(diff_hosts, containers):
    def host_info_request(h, d):
        host_containers = get_host_containers(
            h["host_rescaler_ip"], h["host_rescaler_port"], rescaler_http_session, debug)
        for container_name in host_containers:
            if container_name in container_list_names:
                d[container_name] = host_containers[container_name]

    container_list_names = [c["name"] for c in containers]
    container_info = dict()
    threads = list()
    for hostname in diff_hosts:
        host = diff_hosts[hostname]
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
    diff_hosts = dict()
    for container in containers:
        container_host = container["host"]
        if container_host not in diff_hosts:
            diff_hosts[container_host] = dict()
            diff_hosts[container_host]["host_rescaler_ip"] = container["host_rescaler_ip"]
            diff_hosts[container_host]["host_rescaler_port"] = container["host_rescaler_port"]

    # For each host, retrieve its containers and persist the ones we look for
    # time0 = time.time()
    container_resources_dict = fill_container_dict(diff_hosts, containers)
    # time1 = time.time()

    container_resources_dictV2 = dict()
    for container in containers:
        container_name = container["name"]
        container_resources_dictV2[container_name] = container
        container_resources_dictV2[container_name]["resources"] = container_resources_dict[container_name]

    # p0 = time1 - time0
    # MyUtils.log_info("It took {0} seconds to get containers from hosts (LXD)".format(str("%.2f" % p0)), debug)

    return container_resources_dictV2


def persist_thread():
    t0 = time.time()
    container_resources_dict = get_container_resources_dict()
    # t1 = time.time()
    persist_applications(container_resources_dict)
    # t2 = time.time()
    persist_containers(container_resources_dict)
    t3 = time.time()

    p0 = t3 - t0
    # p1 = t2 - t1
    # p2 = t3 - t2
    # MyUtils.log_info("It took {0} seconds to get container info".format(str("%.2f" % p0)), debug)
    # MyUtils.log_info("It took {0} seconds to snapshot application".format(str("%.2f" % p1)), debug)
    log_info("It took {0} seconds to snapshot containers".format(str("%.2f" % p0)), debug)


def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

    global debug
    myConfig = MyConfig(CONFIG_DEFAULT_VALUES)

    while True:
        # Get service info
        service = get_service(db_handler, SERVICE_NAME) # Remote database operation

        # Heartbeat
        beat(db_handler, SERVICE_NAME) # Remote database operation

        # CONFIG
        myConfig.set_config(service["config"])
        polling_frequency = myConfig.get_config_value("POLLING_FREQUENCY")
        debug = myConfig.get_config_value("DEBUG")

        SERVICE_IS_ACTIVATED = myConfig.get_config_value("ACTIVE")
        thread = None
        if SERVICE_IS_ACTIVATED:
            thread = Thread(target=persist_thread, args=())
            thread.start()
            log_info("Structures snapshoted at {0}".format(get_time_now_string()), debug)
        else:
            log_info("Structure snapshoter is not activated", debug)

        time.sleep(polling_frequency)

        if thread and thread.isAlive():
            delay_start = time.time()
            log_warning(
                "Previous thread didn't finish before next poll is due, with polling time of {0} seconds, at {1}".format(
                    str(polling_frequency), get_time_now_string()), debug)
            log_warning("Going to wait until thread finishes before proceeding", debug)
            thread.join()
            delay_end = time.time()
            log_warning("Resulting delay of: {0} seconds".format(str(delay_end - delay_start)), debug)


def main():
    try:
        persist()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

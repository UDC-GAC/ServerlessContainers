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

import requests
from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import request
import time

import src.Scaler.Scaler
from src.MyUtils import MyUtils
from src.MyUtils.MyUtils import valid_resource, get_host_containers
from src.Orchestrator.utils import get_db, BACK_OFF_TIME_MS, MAX_TRIES
from src.Scaler import Scaler

structure_routes = Blueprint('structures', __name__)

MANDATORY_RESOURCES = ["cpu", "mem"]
CONTAINER_KEYS = ["name", "host_rescaler_ip", "host_rescaler_port", "host", "guard", "subtype"]
HOST_KEYS = ["name", "host", "subtype", "host_rescaler_ip", "host_rescaler_port"]
APP_KEYS = ["name", "guard", "subtype", "resources", "files_dir", "install_script", "start_script", "stop_script", "app_jar"]


def retrieve_structure(structure_name):
    try:
        return get_db().get_structure(structure_name)
    except ValueError:
        return abort(404)


@structure_routes.route("/structure/", methods=['GET'])
def get_structures():
    return jsonify(get_db().get_structures())


@structure_routes.route("/structure/<structure_name>", methods=['GET'])
def get_structure(structure_name):
    return jsonify(retrieve_structure(structure_name))


@structure_routes.route("/structure/<structure_name>/resources", methods=['GET'])
def get_structure_resources(structure_name):
    return jsonify(retrieve_structure(structure_name)["resources"])


@structure_routes.route("/structure/<structure_name>/resources/<resource>", methods=['GET'])
def get_structure_resource(structure_name, resource):
    try:
        return jsonify(retrieve_structure(structure_name)["resources"][resource])
    except KeyError:
        return abort(404)


@structure_routes.route("/structure/<structure_name>/resources/<resource>/<parameter>", methods=['GET'])
def get_structure_parameter_of_resource(structure_name, resource, parameter):
    try:
        return jsonify(retrieve_structure(structure_name)["resources"][resource][parameter])
    except KeyError:
        return abort(404)


@structure_routes.route("/structure/<structure_name>/resources/<resource>/<parameter>", methods=['PUT'])
def set_structure_parameter_of_resource(structure_name, resource, parameter):
    if not valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    if parameter not in ["max", "min", "weight"]:
        return abort(400, {"message": "Invalid parameter state"})

    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
    except KeyError:
        return abort(400)

    structure = retrieve_structure(structure_name)
    if parameter in structure["resources"][resource] and structure["resources"][resource][parameter] == value:
        return jsonify(201)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        structure = retrieve_structure(structure_name)
        structure["resources"][resource][parameter] = value
        get_db().update_structure(structure)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        structure = retrieve_structure(structure_name)
        put_done = structure["resources"][resource][parameter] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


def set_structure_to_guarded_state(structure_name, state):
    if state not in [True, False]:
        return abort(400, {"message": "Invalid guarded state"})

    structure = retrieve_structure(structure_name)

    if "guard" in structure and structure["guard"] == state:
        return jsonify(201)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        structure["guard"] = state
        get_db().update_structure(structure)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        structure = retrieve_structure(structure_name)
        put_done = structure["guard"] == state

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@structure_routes.route("/structure/<structure_name>/guard", methods=['PUT'])
def set_structure_to_guarded(structure_name):
    return set_structure_to_guarded_state(structure_name, True)


@structure_routes.route("/structure/<structure_name>/unguard", methods=['PUT'])
def set_structure_to_unguarded(structure_name):
    return set_structure_to_guarded_state(structure_name, False)


@structure_routes.route("/structure/<structure_name>/resources/<resource>/guard", methods=['PUT'])
def set_structure_resource_to_guarded(structure_name, resource):
    return set_structure_multiple_resources_to_guard_state(structure_name, [resource], True)


@structure_routes.route("/structure/<structure_name>/resources/<resource>/unguard", methods=['PUT'])
def set_structure_resource_to_unguarded(structure_name, resource):
    return set_structure_multiple_resources_to_guard_state(structure_name, [resource], False)


def set_structure_multiple_resources_to_guard_state(structure_name, resources, state):
    structure = retrieve_structure(structure_name)
    if "resources" not in structure:
        return abort(400, {"message": "Structure '{0}' has no resources to configure".format(structure_name)})
    else:
        for resource in resources:
            if not valid_resource(resource):
                return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})
            elif resource not in structure["resources"]:
                return abort(400, {"message": "Resource '{0}' is missing in structure {1}".format(resource, structure_name)})

    # 1st check, in case nothing has to be done really
    put_done = True
    structure = retrieve_structure(structure_name)
    for resource in resources:
        put_done = put_done and structure["resources"][resource]["guard"] == state

    tries = 0
    while not put_done:
        tries += 1
        structure = retrieve_structure(structure_name)
        for resource in resources:
            structure["resources"][resource]["guard"] = state

        get_db().update_structure(structure)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        structure = retrieve_structure(structure_name)

        put_done = True
        for resource in resources:
            put_done = put_done and structure["resources"][resource]["guard"] == state

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def get_resources_to_change_guard_from_request(request):
    resources = None
    data = request.json
    if not data:
        abort(400, {"message": "empty content"})
    try:
        resources = data["resources"]
        if not isinstance(resources, (list, str)):
            abort(400, {"message": "invalid content, resources must be a list or a string"})
    except (KeyError, TypeError):
        abort(400, {"message": "invalid content, must be a json object with resources as key"})
    return resources


@structure_routes.route("/structure/<structure_name>/resources/guard", methods=['PUT'])
def set_structure_multiple_resources_to_guarded(structure_name):
    resources = get_resources_to_change_guard_from_request(request)
    return set_structure_multiple_resources_to_guard_state(structure_name, resources, True)


@structure_routes.route("/structure/<structure_name>/resources/unguard", methods=['PUT'])
def set_structure_multiple_resources_to_unguarded(structure_name):
    resources = get_resources_to_change_guard_from_request(request)
    return set_structure_multiple_resources_to_guard_state(structure_name, resources, False)


@structure_routes.route("/structure/<structure_name>/limits", methods=['GET'])
def get_structure_limits(structure_name):
    try:
        return jsonify(get_db().get_limits(retrieve_structure(structure_name))["resources"])
    except ValueError:
        return abort(404)


@structure_routes.route("/structure/<structure_name>/limits/<resource>", methods=['GET'])
def get_structure_resource_limits(structure_name, resource):
    try:
        return jsonify(get_db().get_limits(retrieve_structure(structure_name))["resources"][resource])
    except ValueError:
        return abort(404)


@structure_routes.route("/structure/<structure_name>/limits/<resource>/boundary", methods=['PUT'])
def set_structure_resource_limit_boundary(structure_name, resource):
    if not valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    try:
        value = int(request.json["value"])
        if value < 0 or value > 100:
            return abort(400)
    except ValueError:
        return abort(500)

    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)

    if "boundary" not in structure_limits["resources"][resource]:
        current_boundary = -1
    else:
        current_boundary = structure_limits["resources"][resource]["boundary"]

    if current_boundary == value:
        pass
    else:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure_limits["resources"][resource]["boundary"] = value
            get_db().update_limit(structure_limits)

            time.sleep(BACK_OFF_TIME_MS / 1000)

            structure = retrieve_structure(structure_name)
            structure_limits = get_db().get_limits(structure)

            put_done = structure_limits["resources"][resource]["boundary"] == value

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


# TODO: Merge with set_structure_resource_limit_boundary
@structure_routes.route("/structure/<structure_name>/limits/<resource>/boundary_type", methods=['PUT'])
def set_structure_resource_limit_boundary_type(structure_name, resource):
    if not valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    try:
        value = str(request.json["value"])
        if value not in ["percentage_of_max", "percentage_of_current"]:
            return abort(400)
    except ValueError:
        return abort(500)

    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)

    if "boundary_type" not in structure_limits["resources"][resource]:
        current_boundary_type = ""
    else:
        current_boundary_type = structure_limits["resources"][resource]["boundary_type"]

    if current_boundary_type == value:
        pass
    else:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure_limits["resources"][resource]["boundary_type"] = value
            get_db().update_limit(structure_limits)

            time.sleep(BACK_OFF_TIME_MS / 1000)

            structure = retrieve_structure(structure_name)
            structure_limits = get_db().get_limits(structure)

            put_done = structure_limits["resources"][resource]["boundary_type"] == value

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def disable_scaler(scaler_service):
    scaler_service["config"]["ACTIVE"] = False
    get_db().update_service(scaler_service)

    # Wait a little bit, half the polling time of the Scaler
    polling_freq = MyUtils.get_config_value(scaler_service["config"], src.Scaler.Scaler.CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
    time.sleep(int(polling_freq))


def restore_scaler_state(scaler_service, previous_state):
    scaler_service["config"]["ACTIVE"] = previous_state
    get_db().update_service(scaler_service)


@structure_routes.route("/structure/container/<structure_name>/<app_name>", methods=['PUT'])
def subscribe_container_to_app(structure_name, app_name):
    structure = retrieve_structure(structure_name)
    app = retrieve_structure(app_name)
    cont_name = structure["name"]

    # Look for any application that hosts this container, to make sure it is not already subscribed
    apps = get_db().get_structures(subtype="application")
    for application in apps:
        if cont_name in application["containers"]:
            return abort(400, {"message": "Container '{0}' already subscribed in app '{1}'".format(cont_name, app_name)})

    app["containers"].append(cont_name)

    get_db().update_structure(app)
    return jsonify(201)


@structure_routes.route("/structure/container/<structure_name>/<app_name>", methods=['DELETE'])
def desubscribe_container_from_app(structure_name, app_name):
    container = retrieve_structure(structure_name)
    app = retrieve_structure(app_name)

    cont_name = container["name"]
    if cont_name not in app["containers"]:
        return abort(400, {"message": "Container '{0}' missing in app '{1}'".format(cont_name, app_name)})
    else:
        app["containers"].remove(cont_name)
        get_db().update_structure(app)
    return jsonify(201)


def free_container_cores(cont_name, host):
    core_map = host["resources"]["cpu"]["core_usage_mapping"]
    freed_shares = 0
    for core in core_map:
        if cont_name in core_map[core]:
            core_shares = core_map[core][cont_name]
            freed_shares += core_shares
            core_map[core][cont_name] = 0
            core_map[core]["free"] += core_shares
    host["resources"]["cpu"]["core_usage_mapping"] = core_map
    host["resources"]["cpu"]["free"] += freed_shares


def free_container_disks(container, host):
    disk_name = container["resources"]["disk"]["name"]
    if "disks" not in host["resources"]:
        return abort(400, {"message": "Host does not have disks"})
    else:
        try:
            current_disk_bw = container["resources"]["disk"]["current"]

            host["resources"]["disks"][disk_name]["free"] += current_disk_bw
            host["resources"]["disks"][disk_name]["load"] -= 1
        except KeyError:
            return abort(400, {"message": "Host does not have requested disk {0}".format(disk_name)})

def free_container_resources(container, host):
    cont_name = container["name"]
    for resource in container["resources"]:
        if resource == 'cpu':
            free_container_cores(cont_name, host)
        elif resource == 'disk':
            free_container_disks(container, host)
        elif resource == 'energy':
            host["resources"][resource]["free"] += container["resources"][resource]["max"]
        else:
            host["resources"][resource]["free"] += container["resources"][resource]["current"]


@structure_routes.route("/structure/container/<structure_name>", methods=['DELETE'])
def desubscribe_container(structure_name):
    container = retrieve_structure(structure_name)
    cont_name = container["name"]

    # Look for any application that hosts this container, and remove it from the list
    apps = get_db().get_structures(subtype="application")
    for app in apps:
        if cont_name in app["containers"]:
            desubscribe_container_from_app(structure_name, app["name"])

    # Disable the Scaler as we will modify the core mapping of a host
    scaler_service = get_db().get_service(src.Scaler.Scaler.SERVICE_NAME)
    previous_state = MyUtils.get_config_value(scaler_service["config"], src.Scaler.Scaler.CONFIG_DEFAULT_VALUES, "ACTIVE")
    if previous_state:
        disable_scaler(scaler_service)

    # Free host resources used by this container
    host = get_db().get_structure(container["host"])
    free_container_resources(container, host)

    get_db().update_structure(host)

    # Delete the document for this container
    get_db().delete_structure(container)

    # Delete the limits for this container
    limits = get_db().get_limits(container)
    get_db().delete_limit(limits)

    # Restore the previous state of the Scaler service
    restore_scaler_state(scaler_service, previous_state)

    return jsonify(201)


def map_container_to_host_cores(cont_name, host, needed_shares):
    core_map = host["resources"]["cpu"]["core_usage_mapping"]
    host_max_cores = int(host["resources"]["cpu"]["max"] / 100)
    host_cpu_list = [str(i) for i in range(host_max_cores)]

    pending_shares = needed_shares
    used_cores = list()

    # Try to satisfy the request by looking and adding a single core
    for core in host_cpu_list:
        if core_map[core]["free"] >= pending_shares:
            core_map[core]["free"] -= pending_shares
            core_map[core][cont_name] = pending_shares
            pending_shares = 0
            used_cores.append(core)
            break

    # Finally, if unsuccessful, add as many cores as necessary, starting with the
    # ones with the largest free shares to avoid too much spread
    if pending_shares > 0:
        l = list()
        for core in host_cpu_list:
            l.append((core, core_map[core]["free"]))
        l.sort(key=lambda tup: tup[1], reverse=True)  # Sort by free shares
        less_used_cores = [i[0] for i in l]

        for core in less_used_cores:
            # If this core has free shares
            if core_map[core]["free"] > 0 and pending_shares > 0:
                if cont_name not in core_map[core]:
                    core_map[core][cont_name] = 0

                # If it has more free shares than needed, assign them and finish
                if core_map[core]["free"] >= pending_shares:
                    core_map[core]["free"] -= pending_shares
                    core_map[core][cont_name] += pending_shares
                    pending_shares = 0
                    used_cores.append(core)
                    break
                else:
                    # Otherwise, assign as many as possible and continue
                    core_map[core][cont_name] += core_map[core]["free"]
                    pending_shares -= core_map[core]["free"]
                    core_map[core]["free"] = 0
                    used_cores.append(core)

    if pending_shares > 0:
        return abort(400, {"message": "Container host does not have enough free CPU shares as requested"})

    host["resources"]["cpu"]["core_usage_mapping"] = core_map
    host["resources"]["cpu"]["free"] -= needed_shares

    return used_cores

def map_container_to_host_disks(resource_dict, container, host):
    disk_name = container["resources"]["disk"]["name"]
    if "disks" not in host["resources"]:
        return abort(400, {"message": "Host does not have disks"})
    else:
        try:
            needed_disk_bw = container["resources"]["disk"]["current"]
            free_disk_bw = host["resources"]["disks"][disk_name]["free"]

            if needed_disk_bw > free_disk_bw:
                return abort(400, {"message": "Container host does not have enough free bandwidth requested on disk {0}".format(disk_name)})

            host["resources"]["disks"][disk_name]["free"] -= needed_disk_bw
            host["resources"]["disks"][disk_name]["load"] += 1
        except KeyError:
            return abort(400, {"message": "Host does not have requested disk {0}".format(disk_name)})

    resource_dict["disk"] = {"disk_read_limit": needed_disk_bw, "disk_write_limit": needed_disk_bw}


def map_container_to_host_resources(container, host):
    cont_name = container["name"]
    resource_dict = {}
    for resource in container["resources"]:
        resource_dict[resource] = {}
        if resource == 'disk':
            map_container_to_host_disks(resource_dict, container, host)
        else:
            needed_amount = container["resources"][resource]["current"]
            if host["resources"][resource]["free"] < needed_amount:
                return abort(400, {"message": "Host does not have enough free {0}".format(resource)})
            if resource == 'cpu':
                resource_dict[resource]["cpu_allowance_limit"] = needed_amount
                used_cores = map_container_to_host_cores(cont_name, host, needed_amount)
                resource_dict[resource]["cpu_num"] = ",".join(used_cores)
            else:
                host["resources"][resource]["free"] -= needed_amount
                resource_dict[resource][f"{resource}_limit"] = needed_amount

    return resource_dict


def check_name_mismatch(name1, name2):
    if name1 != name2:
        return abort(400, {"message": "Name mismatch {0} != {1}".format(name1, name2)})


def check_structure_exists(structure_name, structure_type, searching_for_existence):
    structure_exists = None
    try:
        structure = get_db().get_structure(structure_name)
        if structure:
            structure_exists = True
    except ValueError:
        structure_exists = False

    # If structure exists and we do not want it to exist
    if structure_exists and not searching_for_existence:
        return abort(400, {"message": "Structure {0} with name {1} already exists".format(structure_type, structure_name)})

    # If structure doesn't exist and we want it to exist
    if not structure_exists and searching_for_existence:
        return abort(400, {"message": "Structure {0} with name {1} does not exist".format(structure_type, structure_name)})


def check_resources_data_is_present(data, res_info_type=None):
    if len(res_info_type) > 1:
        for res_info in res_info_type:
            if "resources" not in data[res_info]:
                return abort(400, {"message": "Missing resource {0} information".format(res_info)})
            for resource in MANDATORY_RESOURCES:
                if resource not in data[res_info]["resources"]:
                    return abort(400, {"message": "Missing '{0}' {1} resource information".format(resource, res_info)})
    else:
        res_info = res_info_type[0]
        if "resources" not in data:
            return abort(400, {"message": "Missing resource {0} information".format(res_info)})
        for resource in MANDATORY_RESOURCES:
            if resource not in data["resources"]:
                return abort(400, {"message": "Missing '{0}' {1} resource information".format(resource, res_info)})


def get_resource_keys_from_requested_structure(req_structure, structure, resource, mandatory_keys, optional_keys=[]):
    structure["resources"][resource] = {}
    for key in mandatory_keys:
        if key not in req_structure["resources"][resource]:
            return abort(400, {"message": "Missing key '{0}' for '{1}' resource".format(key, resource)})
        else:
            structure["resources"][resource][key] = req_structure["resources"][resource][key]

    for key in optional_keys:
        if key in req_structure["resources"][resource]:
            structure["resources"][resource][key] = req_structure["resources"][resource][key]

@structure_routes.route("/structure/container/<structure_name>", methods=['PUT'])
def subscribe_container(structure_name):
    node_scaler_session = requests.Session()
    req_cont = request.json["container"]
    req_limits = request.json["limits"]

    # Check that all the needed container data is present on the request
    container = {}
    for key in CONTAINER_KEYS:
        if key not in req_cont:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            container[key] = req_cont[key]
    container["type"] = "structure"

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present(request.json, ["container", "limits"])

    # Check if the container already exists
    check_structure_exists(structure_name, "container", False)

    # Check that its supposed host exists and that it reports this container
    check_structure_exists(container["host"], "host", True)
    host_containers = get_host_containers(container["host_rescaler_ip"], container["host_rescaler_port"], node_scaler_session, True)
    if container["name"] not in host_containers:
        return abort(400, {"message": "Container host does not report any container named '{0}'".format(container["name"])})

    # Check that the endpoint requested container name matches with the one in the request
    check_name_mismatch(container["name"], structure_name)

    # Get data corresponding to container resources
    container["resources"] = {}
    mandatory_resource_keys = ["max", "min", "current", "guard"]
    optional_resource_keys = ["weight"]
    mandatory_keys = {"cpu": mandatory_resource_keys, "mem": mandatory_resource_keys, "energy": mandatory_resource_keys, "disk": ["name", "path"] + mandatory_resource_keys}
    optional_keys = {"cpu": optional_resource_keys, "mem": optional_resource_keys, "energy": optional_resource_keys, "disk": optional_resource_keys}
    for resource in req_cont["resources"]:
        get_resource_keys_from_requested_structure(req_cont, container, resource, mandatory_keys[resource], optional_keys[resource])

    # Get data corresponding to container resource limits
    limits = {"resources": {}}
    for resource in req_limits["resources"]:
        get_resource_keys_from_requested_structure(req_limits, limits, resource, ["boundary", "boundary_type"])
    limits["type"] = 'limit'
    limits["name"] = container["name"]

    # Disable the Scaler as we will modify the core mapping of a host
    scaler_service = get_db().get_service(src.Scaler.Scaler.SERVICE_NAME)
    previous_state = MyUtils.get_config_value(scaler_service["config"], src.Scaler.Scaler.CONFIG_DEFAULT_VALUES, "ACTIVE")
    if previous_state:
        disable_scaler(scaler_service)

    # Get the host info
    host = get_db().get_structure(container["host"])

    resource_dict = map_container_to_host_resources(container, host)
    Scaler.set_container_resources(node_scaler_session, container, resource_dict, True)

    get_db().add_structure(container)
    get_db().update_structure(host)

    # Check if limits already exist
    try:
        existing_limit = get_db().get_limits(container)
        existing_limit['resources'] = limits['resources']
        get_db().update_limit(existing_limit)
    except ValueError:
        # Limits do not exist yet
        get_db().add_limit(limits)

    # Restore the previous state of the Scaler service
    restore_scaler_state(scaler_service, previous_state)

    return jsonify(201)


@structure_routes.route("/structure/host/<structure_name>", methods=['PUT'])
def subscribe_host(structure_name):
    req_host = request.json
    node_scaler_session = requests.Session()

    # Check that all the needed data is present on the request
    host = {}
    for key in HOST_KEYS:
        if key not in req_host:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            host[key] = req_host[key]
    host["type"] = "structure"

    # Check host name in payload and host name in URL are the same
    check_name_mismatch(host["name"], structure_name)

    # Check if the host already exists in StateDatabase
    check_structure_exists(structure_name, "host", False)

    # Check that this supposed host exists and has its node scaler up
    try:
        host_containers = get_host_containers(host["host_rescaler_ip"], host["host_rescaler_port"], node_scaler_session, True)
        if host_containers is None:
            raise RuntimeError()
    except Exception:
        return abort(400, {"message": "Could not connect to this host, is it up and has its node scaler up?"})

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present(req_host, ["host"])

    # Get data corresponding to host resources
    host["resources"] = {}
    for resource in req_host["resources"]:
        if resource == 'disks':
            host["resources"][resource] = {}
            for disk in req_host["resources"][resource]:
                new_disk = {}
                for key in ["type", "load", "path", "max", "free"]:
                    if key not in disk:
                        return abort(400, {"message": "Missing key '{0}' in disk resource information".format(key)})
                    else:
                        new_disk[key] = disk[key]
                host["resources"][resource][disk["name"]] = new_disk
        else:
            get_resource_keys_from_requested_structure(req_host, host, resource, ["max", "free"])

    # Set all host cores free
    host["resources"]["cpu"]["core_usage_mapping"] = {}
    for n in range(0, int(int(host["resources"]["cpu"]["max"]) / 100)):
        host["resources"]["cpu"]["core_usage_mapping"][str(n)] = {"free": 100}

    # Host looks good, insert it into the database
    get_db().add_structure(host)

    return jsonify(201)


@structure_routes.route("/structure/host/<structure_name>", methods=['DELETE'])
def desubscribe_host(structure_name):
    host = retrieve_structure(structure_name)

    # Delete the document for this structure
    get_db().delete_structure(host)

    return jsonify(201)

@structure_routes.route("/structure/apps/<structure_name>", methods=['PUT'])
def subscribe_app(structure_name):
    req_app = request.json["app"]
    req_limits = request.json["limits"]

    # Check that all the needed data is present on the request
    app = {}
    for key in APP_KEYS:
        if key not in req_app:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            app[key] = req_app[key]

    # Check app name in payload and app name in URL are the same
    check_name_mismatch(app["name"], structure_name)

    # Check if the app already exists
    check_structure_exists(structure_name, "application", False)

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present(request.json, ["app", "limits"])

    # Get data corresponding to app resources
    app["resources"] = {}
    for resource in req_app["resources"]:
        get_resource_keys_from_requested_structure(req_app, app, resource, ["max", "min", "guard"], ["weight"])

    app["containers"] = list()
    app["type"] = "structure"

    # Check that all the needed data for resources is present on the requested container LIMITS
    limits = {"resources": {}}
    for resource in req_limits["resources"]:
        get_resource_keys_from_requested_structure(req_limits, limits, resource, ["boundary", "boundary_type"])
    limits["type"] = 'limit'
    limits["name"] = app["name"]

    # Add app to the StateDatabase
    get_db().add_structure(app)

    # Check if limits already exist
    try:
        existing_limit = get_db().get_limits(app)
        existing_limit['resources'] = limits['resources']
        get_db().update_limit(existing_limit)
    except ValueError:
        # Limits do not exist yet
        get_db().add_limit(limits)

    return jsonify(201)


@structure_routes.route("/structure/apps/<structure_name>", methods=['DELETE'])
def desubscribe_app(structure_name):
    app = retrieve_structure(structure_name)

    # Delete the document for this structure
    get_db().delete_structure(app)

    # Delete the limits for this structure
    limits = get_db().get_limits(app)
    get_db().delete_limit(limits)

    return jsonify(201)

@structure_routes.route("/structure/host/<structure_name>/disks", methods=['PUT'])
def add_disks_to_host(structure_name):
    data = request.json

    try:
        host = retrieve_structure(structure_name)
    except ValueError:
        return abort(404, {"message": "Host '{0}' does not exist".format(structure_name)})

    if "resources" not in host:
        return abort(404, {"message": "Missing resource information from host '{0}'".format(host)})

    if "disks" not in host['resources']:
        ## Create disks dict
        host["resources"]["disks"] = {}

    if "resources" not in data or "disks" not in data['resources']:
        return abort(400, {"message": "Missing resource information on request"})

    # Check that all the needed data is present on the request
    for disk in data['resources']['disks']:

        if "name" not in disk:
            return abort(400, {"message": "Missing name disk resource"})

        if disk['name'] in host['resources']['disks']: continue

        new_disk = {}
        for key in ["type", "load", "path", "max", "free"]:
            if key not in disk:
                return abort(400, {"message": "Missing key {0} for disk resource".format(key)})
            else:
                new_disk[key] = disk[key]

        host["resources"]["disks"][disk["name"]] = new_disk

    get_db().update_structure(host)

    return jsonify(201)

@structure_routes.route("/structure/host/<structure_name>/disks", methods=['POST'])
def update_host_disks(structure_name):
    data = request.json

    try:
        host = retrieve_structure(structure_name)
    except ValueError:
        return abort(404, {"message": "Host '{0}' does not exist".format(structure_name)})

    if "resources" not in host or "disks" not in host['resources']:
        return abort(404, {"message": "Missing disk resource information from host '{0}'".format(host)})

    if "resources" not in data or "disks" not in data['resources']:
        return abort(400, {"message": "Missing resource information on request"})

    # Check that all the needed data is present on the request
    for disk in data['resources']['disks']:

        if "name" not in disk:
            return abort(400, {"message": "Missing name disk resource"})

        if disk['name'] not in host['resources']['disks']:
            return abort(404, {"message": "Missing disk {0} in host {1}".format(disk, structure_name)})

        disk_info = host['resources']['disks'][disk['name']]

        busy_bw = 0
        if 'free' in disk_info:
            busy_bw = disk_info['max'] - disk_info['free']

        for key in ["max"]:
            if key not in disk:
                return abort(400, {"message": "Missing key '{0}'".format(key)})
            else:
                disk_info[key] = disk[key]

        ## Update free BW
        disk_info['free'] = disk_info['max'] - busy_bw

    get_db().update_structure(host)

    return jsonify(201)

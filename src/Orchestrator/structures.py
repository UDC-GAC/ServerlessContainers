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

import src.MyUtils.MyUtils as utils
from src.Orchestrator.utils import get_db, BACK_OFF_TIME_MS, MAX_TRIES, get_keys_from_requested_structure, get_resource_keys_from_requested_structure, check_resources_data_is_present, retrieve_structure
from src.Scaler.Scaler import set_container_resources, CONFIG_DEFAULT_VALUES as SCALER_CONFIG_DEFAULTS

structure_routes = Blueprint('structures', __name__)

CONTAINER_KEYS = ["name", "host_rescaler_ip", "host_rescaler_port", "host", "guard", "subtype"]
HOST_KEYS = ["name", "host", "subtype", "host_rescaler_ip", "host_rescaler_port"]
APP_KEYS = ["name", "guard", "subtype", "resources", "install_script", "install_files", "runtime_files", "output_dir", "start_script", "stop_script", "app_jar"]


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
    if not utils.valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    # Energy is a special case where 'current' value may be modified in order to experiment with dynamic power_budgets
    valid_parameters = ["max", "min", "weight"] + (["current"] if resource == "energy" else [])

    if parameter not in valid_parameters:
        return abort(400, {"message": "Invalid parameter state"})

    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
    except KeyError:
        return abort(400)

    structure = retrieve_structure(structure_name)
    if structure.get("resources", {}).get(resource, {}).get(parameter, -1) == value:
        return jsonify(201)

    # If 'current' parameter is being changed, first check is valid
    if parameter == "current":
        _min = structure.get("resources", {}).get(resource, {}).get("min", -1)
        _max = structure.get("resources", {}).get(resource, {}).get("max", -1)
        if not _min <= value <= _max:
            return abort(400, {"message": "Invalid value for 'current' parameter ({0}), it must be "
                                          "between 'min' ({1}) and 'max' ({2})".format(value, _min, _max)})

    put_done = False
    tries = 0
    changes = {"resources": {resource: {parameter: value}}}
    while not put_done:
        tries += 1
        structure["resources"][resource][parameter] = value
        get_db().partial_update_structure(structure, changes)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        structure = retrieve_structure(structure_name)
        put_done = structure["resources"][resource][parameter] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


def set_structure_boolean_parameter(structure_name, parameter, state):
    if state not in [True, False]:
        return abort(400, {"message": "Invalid {0} state".format(parameter)})

    structure = retrieve_structure(structure_name)

    if parameter in structure and structure[parameter] == state:
        return jsonify(201)

    put_done = False
    tries = 0
    changes = {parameter: state}
    while not put_done:
        tries += 1
        structure[parameter] = state
        get_db().partial_update_structure(structure, changes)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        structure = retrieve_structure(structure_name)
        put_done = structure[parameter] == state

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@structure_routes.route("/structure/<structure_name>/run", methods=['PUT'])
def set_structure_to_running(structure_name):
    return set_structure_boolean_parameter(structure_name, "running", True)


@structure_routes.route("/structure/<structure_name>/stop", methods=['PUT'])
def set_structure_to_stop(structure_name):
    return set_structure_boolean_parameter(structure_name, "running", False)


@structure_routes.route("/structure/<structure_name>/guard", methods=['PUT'])
def set_structure_to_guarded(structure_name):
    return set_structure_boolean_parameter(structure_name, "guard", True)


@structure_routes.route("/structure/<structure_name>/unguard", methods=['PUT'])
def set_structure_to_unguarded(structure_name):
    return set_structure_boolean_parameter(structure_name, "guard", False)


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
            if not utils.valid_resource(resource):
                return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})
            if resource not in structure["resources"]:
                return abort(400, {"message": "Resource '{0}' is missing in structure {1}".format(resource, structure_name)})

    # 1st check, in case nothing has to be done really
    put_done = True
    structure = retrieve_structure(structure_name)
    changes = {"resources": {}}
    for resource in resources:
        put_done = put_done and structure["resources"][resource]["guard"] == state
        changes["resources"][resource] = {"guard": state}

    tries = 0
    while not put_done:
        tries += 1
        for resource in resources:
            structure["resources"][resource]["guard"] = state

        get_db().partial_update_structure(structure, changes)

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
    if not utils.valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    try:
        value = int(request.json["value"])
        if value < 0 or value > 100:
            return abort(400)
    except ValueError:
        return abort(500)

    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)

    current_boundary = structure_limits.get("resources", {}).get(resource, {}).get("boundary", -1)
    changes = {"resources": {resource: {"boundary": value}}}

    if current_boundary == value:
        pass
    else:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure_limits["resources"][resource]["boundary"] = value
            get_db().partial_update_limit(structure_limits, changes)

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
    if not utils.valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    try:
        value = str(request.json["value"])
        if value not in ["percentage_of_max", "percentage_of_current"]:
            return abort(400)
    except ValueError:
        return abort(500)

    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)

    current_boundary_type = structure_limits.get("resources", {}).get(resource, {}).get("boundary_type", "")
    changes = {"resources": {resource: {"boundary_type": value}}}
    if current_boundary_type == value:
        pass
    else:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure_limits["resources"][resource]["boundary_type"] = value
            get_db().partial_update_limit(structure_limits, changes)

            time.sleep(BACK_OFF_TIME_MS / 1000)

            structure = retrieve_structure(structure_name)
            structure_limits = get_db().get_limits(structure)

            put_done = structure_limits["resources"][resource]["boundary_type"] == value

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def disable_scaler(scaler_service):
    scaler_service["config"]["ACTIVE"] = False
    get_db().partial_update_service(scaler_service, {"config": {"ACTIVE": False}})

    # Wait a little bit, half the polling time of the Scaler
    polling_freq = scaler_service["config"].get("POLLING_FREQUENCY", SCALER_CONFIG_DEFAULTS["POLLING_FREQUENCY"])
    time.sleep(int(polling_freq))


def restore_scaler_state(scaler_service, previous_state):
    scaler_service["config"]["ACTIVE"] = previous_state
    get_db().partial_update_service(scaler_service, {"config": {"ACTIVE": previous_state}})


@structure_routes.route("/structure/container/<structure_name>/<app_name>", methods=['PUT'])
def subscribe_container_to_app(structure_name, app_name):
    container = retrieve_structure(structure_name)
    app = retrieve_structure(app_name)
    cont_name = container["name"]

    # Look for any application that hosts this container, to make sure it is not already subscribed
    apps = get_db().get_structures(subtype="application")
    for application in apps:
        if cont_name in application["containers"]:
            return abort(400, {"message": "Container '{0}' is already subscribed to app '{1}'".format(cont_name, application["name"])})

    container_changes = {"resources": {}}
    for resource in container["resources"]:
        if resource in app["resources"] and resource != "disk":
            try:
                alloc_ratio = container["resources"][resource]["max"] / app["resources"][resource]["max"]
                container["resources"][resource]["alloc_ratio"] = alloc_ratio
                container_changes["resources"][resource] = {"alloc_ratio": alloc_ratio}
            except (ZeroDivisionError, KeyError) as e:
                return abort(400, {"message": "Couldn't set allocation ratio for container '{0}' and "
                                              "application '{1}': {2}".format(cont_name, app_name, str(e))})

    app["containers"].append(cont_name)

    get_db().partial_update_structure(container, container_changes)
    get_db().partial_update_structure(app, {"containers": app["containers"]})
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
        get_db().partial_update_structure(app, {"containers": app["containers"]})
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

    return {"core_usage_mapping": host["resources"]["cpu"]["core_usage_mapping"], "free": host["resources"]["cpu"]["free"]}


def free_container_disks(container, host):
    disk_name = container["resources"]["disk"]["name"]
    if "disks" not in host["resources"]:
        return abort(400, {"message": "Host does not have disks"})
    else:
        try:
            if "disk_read" not in container["resources"] or "disk_write" not in container["resources"]:
                return abort(400, {"message": "Missing disk read or write bandwidth in container {0}".format(container)})

            current_disk_read_bw = container["resources"]["disk_read"]["current"]
            current_disk_write_bw = container["resources"]["disk_write"]["current"]

            host["resources"]["disks"][disk_name]["free_read"] += current_disk_read_bw
            host["resources"]["disks"][disk_name]["free_write"] += current_disk_write_bw
            host["resources"]["disks"][disk_name]["load"] -= 1
            return {disk_name: {
                "free_read": host["resources"]["disks"][disk_name]["free_read"],
                "free_write": host["resources"]["disks"][disk_name]["free_write"],
                "load": host["resources"]["disks"][disk_name]["load"]
            }}
        except KeyError:
            return abort(400, {"message": "Host does not have requested disk {0}".format(disk_name)})


def free_container_resources(container, host):
    cont_name = container["name"]
    changes = {"resources": {}}
    for resource in container["resources"]:
        if resource == 'cpu':
            changes["resources"]["cpu"] = free_container_cores(cont_name, host)
        elif resource in ['disk_read', 'disk_write']:
            continue
        elif resource == 'disk':
            changes["resources"]["disks"] = free_container_disks(container, host)
        else:
            host["resources"][resource]["free"] += container["resources"][resource]["current"]
            changes["resources"][resource] = {"free": host["resources"][resource]["free"]}
    return changes

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
    scaler_service = get_db().get_service("scaler")
    previous_state = scaler_service["config"].get("ACTIVE", SCALER_CONFIG_DEFAULTS["ACTIVE"])
    if previous_state:
        disable_scaler(scaler_service)

    # Free host resources used by this container
    host = get_db().get_structure(container["host"])
    changes = free_container_resources(container, host)

    get_db().partial_update_structure(host, changes)

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

    return used_cores, {"core_usage_mapping": core_map, "free": host["resources"]["cpu"]["free"]}

def map_container_to_host_disks(resource_dict, container, host):
    disk_name = container["resources"]["disk"]["name"]
    if "disks" not in host["resources"]:
        return abort(400, {"message": "Host does not have disks"})
    else:
        try:
            free_disk_read_bw = host["resources"]["disks"][disk_name]["free_read"]
            free_disk_write_bw = host["resources"]["disks"][disk_name]["free_write"]
        except KeyError:
            return abort(400, {"message": "Host does not have requested disk {0}".format(disk_name)})

        needed_disk_read_bw = container["resources"]["disk_read"]["current"]
        needed_disk_write_bw = container["resources"]["disk_write"]["current"]

        consumed_disk_read_bw = host["resources"]["disks"][disk_name]["max_read"] - free_disk_read_bw
        consumed_disk_write_bw = host["resources"]["disks"][disk_name]["max_write"] - free_disk_write_bw
        total_free = max(host["resources"]["disks"][disk_name]["max_read"], host["resources"]["disks"][disk_name]["max_write"]) - consumed_disk_read_bw - consumed_disk_write_bw

        if needed_disk_read_bw > free_disk_read_bw or needed_disk_write_bw > free_disk_write_bw or needed_disk_read_bw + needed_disk_write_bw > total_free:
            return abort(400, {"message": "Container host does not have enough free bandwidth requested on disk {0}".format(disk_name)})

        host["resources"]["disks"][disk_name]["free_read"] -= needed_disk_read_bw
        host["resources"]["disks"][disk_name]["free_write"] -= needed_disk_write_bw
        host["resources"]["disks"][disk_name]["load"] += 1

        return needed_disk_read_bw, needed_disk_write_bw, {
            disk_name: {"free_read": host["resources"]["disks"][disk_name]["free_read"],
                        "free_write": host["resources"]["disks"][disk_name]["free_write"],
                        "load": host["resources"]["disks"][disk_name]["load"]}
        }

def map_container_to_host_resources(container, host):
    cont_name = container["name"]
    resource_dict = {}
    changes = {"resources": {}}
    for resource in container["resources"]:
        if resource in ['disk_read', 'disk_write']:
            continue
        resource_dict[resource] = {}
        if resource == 'disk':
            read_limit, write_limit, changes["resources"]["disks"] = map_container_to_host_disks(resource_dict, container, host)
            resource_dict["disk_read"] = {"disk_read_limit": read_limit}
            resource_dict["disk_write"] = {"disk_write_limit": write_limit}
        else:
            needed_amount = container["resources"][resource]["current"]
            if host["resources"][resource]["free"] < needed_amount:
                return abort(400, {"message": "Host does not have enough free {0}".format(resource)})
            if resource == 'cpu':
                resource_dict[resource]["cpu_allowance_limit"] = needed_amount
                used_cores, changes["resources"]["cpu"] = map_container_to_host_cores(cont_name, host, needed_amount)
                resource_dict[resource]["cpu_num"] = ",".join(used_cores)
            else:
                host["resources"][resource]["free"] -= needed_amount
                changes["resources"][resource] = {"free": host["resources"][resource]["free"]}
                resource_dict[resource][f"{resource}_limit"] = needed_amount

    return resource_dict, changes


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


@structure_routes.route("/structure/container/<structure_name>", methods=['PUT'])
def subscribe_container(structure_name):
    node_scaler_session = requests.Session()
    req_cont = request.json["container"]
    req_limits = request.json["limits"]

    # Check that all the needed container data is present on the request
    container = get_keys_from_requested_structure(req_cont, CONTAINER_KEYS)

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present(request.json, ["container", "limits"])

    # Check if the container already exists
    check_structure_exists(structure_name, "container", False)

    # Check that its supposed host exists and that it reports this container
    check_structure_exists(container["host"], "host", True)
    host_containers = utils.get_host_containers(container["host_rescaler_ip"], container["host_rescaler_port"], node_scaler_session, True)
    if container["name"] not in host_containers:
        return abort(400, {"message": "Container host does not report any container named '{0}'".format(container["name"])})

    # Check that the endpoint requested container name matches with the one in the request
    check_name_mismatch(container["name"], structure_name)

    # Get data corresponding to container resources
    container["resources"] = {}
    mandatory_resource_keys = ["max", "min", "current", "guard"]
    optional_resource_keys = ["weight"]
    mandatory_keys = {
        "cpu": mandatory_resource_keys,
        "mem": mandatory_resource_keys,
        "energy": mandatory_resource_keys,
        "disk": ["name", "path"],
        "disk_read": mandatory_resource_keys,
        "disk_write": mandatory_resource_keys
    }
    optional_keys = {
        "cpu": optional_resource_keys,
        "mem": optional_resource_keys,
        "energy": optional_resource_keys,
        "disk": [],
        "disk_read": optional_resource_keys,
        "disk_write": optional_resource_keys
    }
    for resource in req_cont["resources"]:
        get_resource_keys_from_requested_structure(req_cont, container, resource, mandatory_keys[resource], optional_keys[resource])

    # Get data corresponding to container resource limits
    limits = {"resources": {}}
    for resource in req_limits["resources"]:
        get_resource_keys_from_requested_structure(req_limits, limits, resource, ["boundary", "boundary_type"])
    limits["type"] = 'limit'
    limits["name"] = container["name"]

    # Disable the Scaler as we will modify the core mapping of a host
    scaler_service = get_db().get_service("scaler")
    previous_state = scaler_service["config"].get("ACTIVE", SCALER_CONFIG_DEFAULTS["ACTIVE"])
    if previous_state:
        disable_scaler(scaler_service)

    # Get the host info
    host = get_db().get_structure(container["host"])
    resource_dict, changes = map_container_to_host_resources(container, host)
    set_container_resources(node_scaler_session, container, resource_dict, True)

    get_db().add_structure(container)
    get_db().partial_update_structure(host, changes)

    # Check if limits already exist
    try:
        existing_limit = get_db().get_limits(container)
        existing_limit['resources'] = limits['resources']
        get_db().partial_update_limit(existing_limit, {"resources": limits['resources']})
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
    host = get_keys_from_requested_structure(req_host, HOST_KEYS)

    # Check host name in payload and host name in URL are the same
    check_name_mismatch(host["name"], structure_name)

    # Check if the host already exists in StateDatabase
    check_structure_exists(structure_name, "host", False)

    # Check that this supposed host exists and has its node scaler up
    try:
        host_containers = utils.get_host_containers(host["host_rescaler_ip"], host["host_rescaler_port"], node_scaler_session, True)
        if host_containers is None:
            raise RuntimeError()
    except Exception:
        return abort(400, {"message": "Could not connect to this host, is it up and has its node scaler up?"})

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present({"host": req_host}, ["host"])

    # Get data corresponding to host resources
    host["resources"] = {}
    for resource in req_host["resources"]:
        if resource == 'disks':
            host["resources"][resource] = {}
            for disk in req_host["resources"][resource]:
                new_disk = {}
                for key in ["type", "load", "path", "max_read", "free_read", "max_write", "free_write"]:
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
    app = get_keys_from_requested_structure(req_app, APP_KEYS, ["framework"])

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

    app["containers"] = []
    app["running"] = req_app.get("running", False)

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
        get_db().partial_update_limit(existing_limit, {"resources": limits['resources']})
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
    changes = {"resources": {"disks": {}}}
    for disk in data['resources']['disks']:

        if "name" not in disk:
            return abort(400, {"message": "Missing name disk resource"})

        if disk['name'] in host['resources']['disks']: continue

        new_disk = {}
        for key in ["type", "load", "path", "max_read", "free_read", "max_write", "free_write"]:
            if key not in disk:
                return abort(400, {"message": "Missing key {0} for disk resource".format(key)})
            else:
                new_disk[key] = disk[key]

        host["resources"]["disks"][disk["name"]] = new_disk
        changes["resources"]["disks"][disk["name"]] = new_disk

    get_db().partial_update_structure(host, changes)

    return jsonify(201)

## Used when extending LV
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
    changes = {"resources": {"disks": {}}}
    for disk in data['resources']['disks']:

        if "name" not in disk:
            return abort(400, {"message": "Missing name disk resource"})

        if disk['name'] not in host['resources']['disks']:
            return abort(404, {"message": "Missing disk {0} in host {1}".format(disk, structure_name)})

        disk_info = host['resources']['disks'][disk['name']]
        changes["resources"]["disks"][disk['name']] = {}
        for max_key, free_key in [("max_read", "free_read"), ("max_write", "free_write")]:
            if max_key not in disk:
                return abort(400, {"message": "Missing key '{0}'".format(max_key)})

            busy_bw = disk_info[max_key] - disk_info[free_key]
            disk_info[max_key] = disk[max_key]
            changes["resources"]["disks"][disk['name']][max_key] = disk[max_key]

            ## Update free BW
            disk_info[free_key] = disk_info[max_key] - busy_bw
            changes["resources"]["disks"][disk['name']][free_key] = disk_info[max_key] - busy_bw

    get_db().partial_update_structure(host, changes)

    return jsonify(201)

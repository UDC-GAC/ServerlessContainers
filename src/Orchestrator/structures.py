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

    if parameter not in ["max", "min"]:
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
        structure = retrieve_structure(structure_name)
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
        if value < 0:
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


@structure_routes.route("/structure/container/<structure_name>", methods=['DELETE'])
def desubscribe_container(structure_name):
    structure = retrieve_structure(structure_name)
    cont_name = structure["name"]

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

    # Free resources

    # CPU
    # Get the core map of the container's host and free the allocated shares for this container
    cont_host = structure["host"]
    host = get_db().get_structure(cont_host)
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

    # MEM
    host["resources"]["mem"]["free"] += structure["resources"]["mem"]["current"]

    # Decrease disk load and increase free bw
    if 'disk' in structure["resources"]:
        disk_name = structure["resources"]["disk"]["name"]
        if "disks" not in host["resources"]:
            return abort(400, {"message": "Host does not have disks"})
        else:
            try:
                current_disk_bw = structure["resources"]["disk"]["current"]

                host["resources"]["disks"][disk_name]["free"] += current_disk_bw
                host["resources"]["disks"][disk_name]["load"] -= 1
            except KeyError:
                return abort(400, {"message": "Host does not have requested disk {0}".format(disk_name)})

    get_db().update_structure(host)

    # Delete the document for this structure
    get_db().delete_structure(structure)

    # Delete the limits for this structure
    limits = get_db().get_limits(structure)
    get_db().delete_limit(limits)

    # Restore the previous state of the Scaler service
    restore_scaler_state(scaler_service, previous_state)

    return jsonify(201)


@structure_routes.route("/structure/container/<structure_name>", methods=['PUT'])
def subscribe_container(structure_name):
    req_cont = request.json["container"]
    req_limits = request.json["limits"]

    node_scaler_session = requests.Session()

    # Check that all the needed data is present on the requestes container
    container = {}
    for key in ["name", "host_rescaler_ip", "host_rescaler_port", "host", "guard", "subtype"]:
        if key not in req_cont:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            container[key] = req_cont[key]

    # Check that all the needed data for resources is present on the requested container
    container["resources"] = {}
    if "resources" not in req_cont:
        return abort(400, {"message": "Missing resource information"})
    elif "cpu" not in req_cont["resources"] or "mem" not in req_cont["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information"})
    else:
        container["resources"] = {"cpu": {}, "mem": {}}
        for key in ["max", "min", "current", "guard"]:
            if key not in req_cont["resources"]["cpu"] or key not in req_cont["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                container["resources"]["cpu"][key] = req_cont["resources"]["cpu"][key]
                container["resources"]["mem"][key] = req_cont["resources"]["mem"][key]

        if 'disk' in req_cont["resources"]:
            disk = req_cont["resources"]["disk"]
            container["resources"]["disk"] = {}
            for key in ["name", "path", "max", "min", "current", "guard"]:
                if key not in disk:
                    return abort(400, {"message": "Missing key {0} for disk resource".format(req_cont)})
                else:
                    container["resources"]["disk"][key] = disk[key]

    # Check that the endpoint requested container name matches with the one in the request
    if container["name"] != structure_name:
        return abort(400, {"message": "Name mismatch".format(key)})

    # Check if the container already exists
    try:
        cont = get_db().get_structure(structure_name)
        if cont:
            return abort(400, {"message": "Container with this name already exists".format(key)})
    except ValueError:
        pass

    # Check that its supposed host exists and that it reports this container
    try:
        get_db().get_structure(container["host"])
    except ValueError:
        return abort(400, {"message": "Container host does not exist".format(key)})
    host_containers = get_host_containers(container["host_rescaler_ip"], container["host_rescaler_port"], node_scaler_session, True)

    if container["name"] not in host_containers:
        return abort(400, {"message": "Container host does not report any container named '{0}'".format(container["name"])})

    container["type"] = "structure"

    # Check that all the needed data for resources is present on the requested container LIMITS
    limits = {}
    if "resources" not in req_limits:
        return abort(400, {"message": "Missing resource information for the limits"})
    elif "cpu" not in req_limits["resources"] or "mem" not in req_limits["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information for the limits"})
    else:
        limits["resources"] = {"cpu": {}, "mem": {}}
        for key in ["boundary"]:
            if key not in req_limits["resources"]["cpu"] or key not in req_limits["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                limits["resources"]["cpu"][key] = req_limits["resources"]["cpu"][key]
                limits["resources"]["mem"][key] = req_limits["resources"]["mem"][key]

    if 'disk' in req_limits["resources"]:
        limits["resources"]["disk"] = {}
        for key in ["boundary"]:
            if key not in req_limits["resources"]["disk"]:
                return abort(400, {"message": "Missing key '{0}' for disk resource".format(key)})
            else:
                limits["resources"]["disk"][key] = req_limits["resources"]["disk"][key]

    limits["type"] = 'limit'
    limits["name"] = container["name"]


    #### ALL looks good up to this point, proceed

    # Disable the Scaler as we will modify the core mapping of a host
    scaler_service = get_db().get_service(src.Scaler.Scaler.SERVICE_NAME)
    previous_state = MyUtils.get_config_value(scaler_service["config"], src.Scaler.Scaler.CONFIG_DEFAULT_VALUES, "ACTIVE")
    if previous_state:
        disable_scaler(scaler_service)

    # Get the host info
    cont_host = container["host"]
    cont_name = container["name"]
    host = get_db().get_structure(cont_host)

    # CPU

    # Look for resource shares on the container's host
    needed_shares = container["resources"]["cpu"]["current"]
    if host["resources"]["cpu"]["free"] < needed_shares:
        return abort(400, {"message": "Host does not have enough shares".format(key)})

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

    # Finally, if unsuccessful, add as many cores as necessary, starting with the ones with the largest free shares to avoid too much spread
    if pending_shares > 0:
        l = list()
        for core in host_cpu_list:
            l.append((core, core_map[core]["free"]))
        l.sort(key=lambda tup: tup[1], reverse=True)
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

    # MEM
    needed_memory = container["resources"]["mem"]["current"]
    host_memory = host["resources"]["mem"]["free"]

    if needed_memory > host_memory:
        return abort(400, {"message": "Container host does not have enough free memory requested"})

    host["resources"]["mem"]["free"] -= needed_memory

    resource_dict = {"cpu": {"cpu_num": ",".join(used_cores), "cpu_allowance_limit": needed_shares},
                     "mem": {"mem_limit": needed_memory}}

    # Increase disk load and decrease free bw
    if 'disk' in req_cont["resources"]:
        disk_name = req_cont["resources"]["disk"]["name"]
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
    data = request.json
    node_scaler_session = requests.Session()

    # Check that all the needed data is present on the request
    host = {}
    for key in ["name", "host", "subtype", "host_rescaler_ip", "host_rescaler_port"]:
        if key not in data:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            host[key] = data[key]

    # Check that all the needed data for resources is present on the request
    host["resources"] = {}
    if "resources" not in data:
        return abort(400, {"message": "Missing resource information"})
    elif "cpu" not in data["resources"] or "mem" not in data["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information"})
    else:
        host["resources"] = {"cpu": {}, "mem": {}}
        for key in ["max", "free"]:
            if key not in data["resources"]["cpu"] or key not in data["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                host["resources"]["cpu"][key] = data["resources"]["cpu"][key]
                host["resources"]["mem"][key] = data["resources"]["mem"][key]

        host["resources"]["cpu"]["core_usage_mapping"] = {}
        for n in range(0, int(host["resources"]["cpu"]["max"] / 100)):
            host["resources"]["cpu"]["core_usage_mapping"][n] = {"free": 100}

        if 'disks' in data["resources"]:
            disks = data["resources"]["disks"]
            host["resources"]["disks"] = {}
            for disk in disks:
                if "name" not in disk:
                    return abort(400, {"message": "Missing name disk resource"})
                new_disk = {}
                for key in ["type", "load", "path", "max", "free"]:
                    if key not in disk:
                        return abort(400, {"message": "Missing key {0} for disk resource".format(key)})
                    else:
                        new_disk[key] = disk[key]
                host["resources"]["disks"][disk["name"]] = new_disk

    if host["name"] != structure_name:
        return abort(400, {"message": "Name mismatch".format(key)})

    # Check if the host already exists
    try:
        host = get_db().get_structure(structure_name)
        if host:
            return abort(400, {"message": "Host with this name already exists".format(key)})
    except ValueError:
        pass

    # Check that this supposed host exists and that it reports this container
    try:
        host_containers = get_host_containers(host["host_rescaler_ip"], host["host_rescaler_port"], node_scaler_session, True)
        if host_containers == None:
            raise RuntimeError()
    except Exception:
        return abort(400, {"message": "Could not connect to this host, is it up and has its node scaler up?"})

    # Host looks good, insert it into the database
    host["type"] = "structure"

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
    req_limits  = request.json["limits"]

    # Check that all the needed data is present on the request
    app = {}
    for key in ["name", "guard", "subtype", "resources", "files_dir", "install_script", "start_script", "stop_script", "app_jar"]:
        if key not in req_app:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            app[key] = req_app[key]

    # Check that all the needed data for resources is present on the request
    app["resources"] = {}
    if "resources" not in req_app:
        return abort(400, {"message": "Missing resource information"})
    elif "cpu" not in req_app["resources"] or "mem" not in req_app["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information"})
    else:
        app["resources"] = {"cpu": {}, "mem": {}}
        for key in ["max", "min", "guard"]:
            if key not in req_app["resources"]["cpu"] or key not in req_app["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                app["resources"]["cpu"][key] = req_app["resources"]["cpu"][key]
                app["resources"]["mem"][key] = req_app["resources"]["mem"][key]

        if 'disk' in req_app["resources"]:
            disk = req_app["resources"]["disk"]
            app["resources"]["disk"] = {}
            for key in ["max", "min", "guard"]:
                if key not in disk:
                    return abort(400, {"message": "Missing key {0} for disk resource".format(key)})
                else:
                    app["resources"]["disk"][key] = disk[key]

    if app["name"] != structure_name:
        return abort(400, {"message": "Name mismatch".format(key)})

    # Check if the app already exists
    try:
        app = get_db().get_structure(structure_name)
        if app:
            return abort(400, {"message": "App with this name already exists".format(key)})
    except ValueError:
        pass

    #### ALL looks good up to this point, proceed
    app["containers"] = list()
    app["type"] = "structure"

    # Check that all the needed data for resources is present on the requested container LIMITS
    limits = {}
    if "resources" not in req_limits:
        return abort(400, {"message": "Missing resource information for the limits"})
    elif "cpu" not in req_limits["resources"] or "mem" not in req_limits["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information for the limits"})
    else:
        limits["resources"] = {"cpu": {}, "mem": {}}
        for key in ["boundary"]:
            if key not in req_limits["resources"]["cpu"] or key not in req_limits["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                limits["resources"]["cpu"][key] = req_limits["resources"]["cpu"][key]
                limits["resources"]["mem"][key] = req_limits["resources"]["mem"][key]

        if 'disk' in req_limits["resources"]:
            limits["resources"]["disk"] = {}
            for key in ["boundary"]:
                if key not in req_limits["resources"]["disk"]:
                    return abort(400, {"message": "Missing key '{0}' for disk resource".format(key)})
                else:
                    limits["resources"]["disk"][key] = req_limits["resources"]["disk"][key]

    limits["type"] = 'limit'
    limits["name"] = app["name"]

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

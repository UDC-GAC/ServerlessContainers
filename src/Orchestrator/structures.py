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


@structure_routes.route("/structure/<structure_name>/<app_name>", methods=['PUT'])
def subscribe_container_to_app(structure_name, app_name):
    structure = retrieve_structure(structure_name)
    app = retrieve_structure(app_name)
    cont_name = structure["name"]

    # Look for any application that hosts this container, to make sure it is not already subscribed
    apps = get_db().get_structures(subtype="application")
    for app in apps:
        if cont_name in app["containers"]:
            return abort(400, {"message": "Container '{0}' already subscribed in app '{1}'".format(cont_name, app_name)})

    app["containers"].append(cont_name)

    get_db().update_structure(app)
    return jsonify(201)


@structure_routes.route("/structure/<structure_name>/<app_name>", methods=['DELETE'])
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


@structure_routes.route("/structure/<structure_name>", methods=['DELETE'])
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
    get_db().update_structure(host)

    # Delete the document for this structure
    get_db().delete_structure(structure)

    # Restore the previous state of the Scaler service
    restore_scaler_state(scaler_service, previous_state)

    return jsonify(201)


@structure_routes.route("/structure/<structure_name>", methods=['PUT'])
def subscribe_container(structure_name):
    data = request.json
    node_scaler_session = requests.Session()

    # Check that all the needed data is present on the request
    container = {}
    for key in ["name", "host_rescaler_ip", "host_rescaler_port", "host", "guard", "subtype"]:
        if key not in data:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            container[key] = data[key]

    # Check that all the needed data for resources is present on the request
    container["resources"] = {}
    if "resources" not in data:
        return abort(400, {"message": "Missing resource information"})
    elif "cpu" not in data["resources"] or "mem" not in data["resources"]:
        return abort(400, {"message": "Missing cpu or mem resource information"})
    else:
        container["resources"] = {"cpu": {}, "mem": {}}
        for key in ["max", "min", "current"]:
            if key not in data["resources"]["cpu"] or key not in data["resources"]["mem"]:
                return abort(400, {"message": "Missing key '{0}' for cpu or mem resource".format(key)})
            else:
                container["resources"]["cpu"][key] = data["resources"]["cpu"][key]
                container["resources"]["mem"][key] = data["resources"]["mem"][key]

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
        cont_host = get_db().get_structure(container["host"])
    except ValueError:
        return abort(400, {"message": "Container host does not exist".format(key)})
    host_containers = get_host_containers(container["host_rescaler_ip"], container["host_rescaler_port"], node_scaler_session, True)
    print(host_containers)
    if container["name"] not in host_containers:
        return abort(400, {"message": "Container host does not report any container named '{0}'".format(container["name"])})

    #### ALL looks good up to this point, proceed

    # Disable the Scaler as we will modify the core mapping of a host
    scaler_service = get_db().get_service(src.Scaler.Scaler.SERVICE_NAME)
    previous_state = MyUtils.get_config_value(scaler_service["config"], src.Scaler.Scaler.CONFIG_DEFAULT_VALUES, "ACTIVE")
    if previous_state:
        disable_scaler(scaler_service)

    # Look for resource shares on the container's host
    cont_host = container["host"]
    cont_name = container["name"]
    host = get_db().get_structure(cont_host)

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
            core_map[core][cont_name] += pending_shares
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

    host["resources"]["cpu"]["core_usage_mapping"] = core_map
    host["resources"]["cpu"]["free"] -= needed_shares

    resource_dict = {"cpu": {"cpu_num": ",".join(used_cores), "cpu_allowance_limit": needed_shares}}
    Scaler.set_container_resources(node_scaler_session, container, resource_dict, True)

    get_db().add_structure(container)
    get_db().update_structure(host)

    # Restore the previous state of the Scaler service
    restore_scaler_state(scaler_service, previous_state)

    return jsonify(201)
#
# def set_structure_guard_policy(structure_name, policy):
#     try:
#         put_done = False
#         tries = 0
#         while not put_done:
#             tries += 1
#             structure = retrieve_structure(structure_name)
#             new_structure = MyUtils.copy_structure_base(structure)
#             new_structure["guard_policy"] = policy
#             get_db().update_structure(new_structure)
#
#             time.sleep(BACK_OFF_TIME_MS / 1000)
#             structure = retrieve_structure(structure_name)
#             put_done = structure["guard_policy"] == policy
#
#             if tries >= MAX_TRIES:
#                 return abort(400, {"message": "MAX_TRIES updating database document"})
#
#     except ValueError:
#         return abort(404)
#     return jsonify(201)
#
#
# @structure_routes.route("/structure/<structure_name>/guard_policy/serverless", methods=['PUT'])
# def set_structure_guard_policy_to_serverless(structure_name):
#     return set_structure_guard_policy(structure_name, "serverless")
#
#
# @structure_routes.route("/structure/<structure_name>/guard_policy/fixed", methods=['PUT'])
# def set_structure_guard_policy_to_fixed(structure_name):
#     return set_structure_guard_policy(structure_name, "fixed")

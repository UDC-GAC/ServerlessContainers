from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import request
import time

from src.MyUtils import MyUtils
from src.MyUtils.MyUtils import valid_resource
from src.Orchestrator.utils import get_db, BACK_OFF_TIME, MAX_TRIES

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

    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
    except KeyError:
        return abort(400)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        structure = retrieve_structure(structure_name)
        new_structure = MyUtils.copy_structure_base(structure)
        new_structure["resources"] = {resource: {parameter: value}}
        get_db().update_structure(new_structure)

        time.sleep(BACK_OFF_TIME)
        structure = retrieve_structure(structure_name)
        put_done = structure["resources"][resource][parameter] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def set_structure_to_guarded_state(structure_name, state):
    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        ###
        structure = retrieve_structure(structure_name)
        if structure["guard"] == state:
            put_done = True
        else:
            new_structure = MyUtils.copy_structure_base(structure)
            new_structure["guard"] = state
            get_db().update_structure(new_structure)

            time.sleep(BACK_OFF_TIME)
            structure = retrieve_structure(structure_name)
            put_done = structure["guard"] == state
        ###
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
    tries = 0
    put_done = False
    while not put_done:
        tries += 1
        structure = retrieve_structure(structure_name)
        new_structure = MyUtils.copy_structure_base(structure)
        new_structure["resources"] = dict()
        for resource in resources:
            if not valid_resource(resource):
                return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

        for resource in resources:
            new_structure["resources"][resource] = {"guard": state}
        get_db().update_structure(new_structure)

        time.sleep(BACK_OFF_TIME)
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

    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)
    current_boundary = -1
    try:
        current_boundary = structure_limits["resources"][resource]["boundary"]
    except KeyError:
        abort(404)
    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
        int(current_boundary)
    except ValueError:
        return abort(500)

    if current_boundary == value:
        pass
    else:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure_limits["resources"][resource]["boundary"] = value
            get_db().update_limit(structure_limits)

            time.sleep(BACK_OFF_TIME)
            structure = retrieve_structure(structure_name)
            structure_limits = get_db().get_limits(structure)

            put_done = structure_limits["resources"][resource]["boundary"] == value

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def set_structure_guard_policy(structure_name, policy):
    try:
        put_done = False
        tries = 0
        while not put_done:
            tries += 1
            structure = retrieve_structure(structure_name)
            new_structure = MyUtils.copy_structure_base(structure)
            new_structure["guard_policy"] = policy
            get_db().update_structure(new_structure)

            time.sleep(BACK_OFF_TIME)
            structure = retrieve_structure(structure_name)
            put_done = structure["guard_policy"] == policy

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    except ValueError:
        return abort(404)
    return jsonify(201)


@structure_routes.route("/structure/<structure_name>/guard_policy/serverless", methods=['PUT'])
def set_structure_guard_policy_to_serverless(structure_name):
    return set_structure_guard_policy(structure_name, "serverless")


@structure_routes.route("/structure/<structure_name>/guard_policy/fixed", methods=['PUT'])
def set_structure_guard_policy_to_fixed(structure_name):
    return set_structure_guard_policy(structure_name, "fixed")
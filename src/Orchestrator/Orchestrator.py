#!/usr/bin/python
import json
import time
from flask import Flask, g
from flask import Response
from flask import abort
from flask import jsonify
from flask import request


import src.StateDatabase.couchdb as couchDB
import src.MyUtils.MyUtils as MyUtils

app = Flask(__name__)

MAX_TRIES = 10


def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if not hasattr(g, 'db_handler'):
        g.db_handler = couchDB.CouchDBServer()
    return g.db_handler


def retrieve_service(service_name):
    try:
        return get_db().get_service(service_name)
    except ValueError:
        return abort(404)


@app.route("/service/", methods=['GET'])
def get_services():
    return jsonify(get_db().get_services())


@app.route("/service/<service_name>", methods=['GET'])
def get_service(service_name):
    return jsonify(retrieve_service(service_name))


@app.route("/service/<service_name>", methods=['PUT'])
def set_service_information(service_name):
    data = request.json
    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        service = retrieve_service(service_name)
        for key in data:
            service["config"][key] = data[key]
        get_db().update_service(service)

        put_done = True
        service = retrieve_service(service_name)
        for key in data:
            put_done = put_done and service["config"][key] == data[key]

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


@app.route("/service/<service_name>/<key>", methods=['PUT'])
def set_service_value(service_name, key):
    put_done = False
    tries = 0
    value = int(request.json["value"])
    while not put_done:
        tries += 1
        service = retrieve_service(service_name)
        service["config"][key] = value
        get_db().update_service(service)

        service = retrieve_service(service_name)
        put_done = service["config"][key] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


def retrieve_rule(rule_name):
    try:
        return get_db().get_rule(rule_name)
    except ValueError:
        return abort(404)


@app.route("/rule/", methods=['GET'])
def get_rules():
    return jsonify(get_db().get_rules())


@app.route("/rule/<rule_name>", methods=['GET'])
def get_rule(rule_name):
    return jsonify(retrieve_rule(rule_name))


@app.route("/rule/<rule_name>/activate", methods=['PUT'])
def activate_rule(rule_name):
    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        rule = retrieve_rule(rule_name)
        rule["active"] = True
        get_db().update_rule(rule)
        rule = retrieve_rule(rule_name)
        put_done = rule["active"]
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@app.route("/rule/<rule_name>/deactivate", methods=['PUT'])
def deactivate_rule(rule_name):
    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        rule = retrieve_rule(rule_name)
        rule["active"] = False
        get_db().update_rule(rule)
        rule = retrieve_rule(rule_name)
        put_done = not rule["active"]
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


def retrieve_structure(structure_name):
    try:
        return get_db().get_structure(structure_name)
    except ValueError:
        return abort(404)


@app.route("/structure/", methods=['GET'])
def get_structures():
    return jsonify(get_db().get_structures())


@app.route("/structure/<structure_name>", methods=['GET'])
def get_structure(structure_name):
    return jsonify(retrieve_structure(structure_name))


@app.route("/structure/<structure_name>/resources", methods=['GET'])
def get_structure_resources(structure_name):
    return jsonify(retrieve_structure(structure_name)["resources"])


@app.route("/structure/<structure_name>/resources/<resource>", methods=['GET'])
def get_structure_resource(structure_name, resource):
    try:
        return jsonify(retrieve_structure(structure_name)["resources"][resource])
    except KeyError:
        return abort(404)


@app.route("/structure/<structure_name>/resources/<resource>/<parameter>", methods=['GET'])
def get_structure_parameter_of_resource(structure_name, resource, parameter):
    try:
        return jsonify(retrieve_structure(structure_name)["resources"][resource][parameter])
    except KeyError:
        return abort(404)


@app.route("/structure/<structure_name>/resources/<resource>/<parameter>", methods=['PUT'])
def set_structure_parameter_of_resource(structure_name, resource, parameter):
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
        structure = retrieve_structure(structure_name)
        new_structure = MyUtils.copy_structure_base(structure)
        new_structure["guard"] = state
        get_db().update_structure(new_structure)
        time.sleep(2)
        structure = retrieve_structure(structure_name)
        put_done = structure["guard"] == state
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@app.route("/structure/<structure_name>/guard", methods=['PUT'])
def set_structure_to_guarded(structure_name):
    return set_structure_to_guarded_state(structure_name, True)


@app.route("/structure/<structure_name>/unguard", methods=['PUT'])
def set_structure_to_unguarded(structure_name):
    return set_structure_to_guarded_state(structure_name, False)


@app.route("/structure/<structure_name>/resources/<resource>/guard", methods=['PUT'])
def set_structure_resource_to_guarded(structure_name, resource):
    return set_structure_multiple_resources_to_guard_state(structure_name, [resource], True)


@app.route("/structure/<structure_name>/resources/<resource>/unguard", methods=['PUT'])
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
            if resource not in ["cpu", "mem", "disk", "net", "energy"]:
                continue
            else:
                new_structure["resources"][resource] = {"guard": state}
        get_db().update_structure(new_structure)

        time.sleep(2)
        structure = retrieve_structure(structure_name)
        put_done = True
        for resource in resources:
            if resource not in ["cpu", "mem", "disk", "net", "energy"]:
                continue
            else:
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
        elif isinstance(resources, str):
            resources = [resources]
    except (KeyError, TypeError):
        abort(400, {"message": "invalid content, must be a json object with resources as key"})
    return resources


@app.route("/structure/<structure_name>/resources/guard", methods=['PUT'])
def set_structure_multiple_resources_to_guarded(structure_name):
    resources = get_resources_to_change_guard_from_request(request)
    return set_structure_multiple_resources_to_guard_state(structure_name, resources, True)


@app.route("/structure/<structure_name>/resources/unguard", methods=['PUT'])
def set_structure_multiple_resources_to_unguarded(structure_name):
    resources = get_resources_to_change_guard_from_request(request)
    return set_structure_multiple_resources_to_guard_state(structure_name, resources, False)


@app.route("/structure/<structure_name>/limits", methods=['GET'])
def get_structure_limits(structure_name):
    try:
        return jsonify(get_db().get_limits(retrieve_structure(structure_name))["resources"])
    except ValueError:
        return abort(404)


@app.route("/structure/<structure_name>/limits/<resource>", methods=['GET'])
def get_structure_resource_limits(structure_name, resource):
    try:
        return jsonify(get_db().get_limits(retrieve_structure(structure_name))["resources"][resource])
    except ValueError:
        return abort(404)


@app.route("/structure/<structure_name>/limits/<resource>/boundary", methods=['PUT'])
def set_structure_resource_limit_boundary(structure_name, resource):
    structure = retrieve_structure(structure_name)
    structure_limits = get_db().get_limits(structure)
    try:
        bogus = structure_limits["resources"][resource]["boundary"]
    except KeyError:
        abort(404)

    value = int(request.json["value"])
    if value < 0:
        return abort(400)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        structure_limits["resources"][resource]["boundary"] = value
        get_db().update_limit(structure_limits)

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

            structure = retrieve_structure(structure_name)
            put_done = structure["guard_policy"] == policy

            if tries >= MAX_TRIES:
                return abort(400, {"message": "MAX_TRIES updating database document"})

    except ValueError:
        return abort(404)
    return jsonify(201)


@app.route("/structure/<structure_name>/guard_policy/serverless", methods=['PUT'])
def set_structure_guard_policy_to_serverless(structure_name):
    return set_structure_guard_policy(structure_name, "serverless")


@app.route("/structure/<structure_name>/guard_policy/fixed", methods=['PUT'])
def set_structure_guard_policy_to_fixed(structure_name):
    return set_structure_guard_policy(structure_name, "fixed")


@app.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

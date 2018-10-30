#!/usr/bin/python
import json
from flask import Flask, g
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
import StateDatabase.couchDB as couchDB
from MyUtils import MyUtils

app = Flask(__name__)


def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if not hasattr(g, 'db_handler'):
        g.db_handler = couchDB.CouchDBServer()
    return g.db_handler


@app.route("/profile/", methods=['GET'])
def get_profiles():
    return jsonify(get_db().get_profiles())


@app.route("/profile/<profile_name>", methods=['GET'])
def get_profile(profile_name):
    try:
        profile = get_db().get_profile(profile_name)
    except ValueError:
        return abort(404)
    return jsonify(profile)


@app.route("/profile/<profile_name>", methods=['PUT'])
def set_profile(profile_name):
    data = request.json
    if not data:
        return abort(400, {"message": "empty content"})

    try:
        profile = get_db().get_profile(profile_name)
    except ValueError:
        return abort(404)

    for key in data:
        if key in ["_id", "_rev", "name", "type"]:
            continue
        else:
            profile[key] = data[key]
    get_db().update_profile(profile)
    return jsonify(profile)


@app.route("/service/", methods=['GET'])
def get_services():
    return jsonify(get_db().get_services())


@app.route("/service/<service_name>", methods=['GET'])
def get_service(service_name):
    try:
        service = get_db().get_service(service_name)
    except ValueError:
        return abort(404)
    return jsonify(service)


@app.route("/service/<service_name>", methods=['PUT'])
def set_service_information(service_name):
    if service_name == "":
        abort(400)

    try:
        service = get_db().get_service(service_name)
    except ValueError:
        return abort(404)

    data = request.json
    for key in data:
        service["config"][key] = data[key]

    get_db().update_service(service)

    return jsonify(201)


@app.route("/service/<service_name>/<key>", methods=['PUT'])
def set_service_value(service_name, key):
    if service_name == "":
        abort(400)

    try:
        service = get_db().get_service(service_name)
    except ValueError:
        return abort(404)

    value = int(request.json["value"])
    service["config"][key] = value

    get_db().update_service(service)

    return jsonify(201)


@app.route("/rule/", methods=['GET'])
def get_rules():
    return jsonify(get_db().get_rules())


@app.route("/rule/<rule_name>", methods=['GET'])
def get_rule(rule_name):
    return jsonify(get_db().get_rule(rule_name))


@app.route("/rule/<rule_name>", methods=['PUT'])
def set_rule(rule_name):
    pass


@app.route("/rule/<rule_name>/activate", methods=['PUT'])
def activate_rule(rule_name):
    rule = get_db().get_rule(rule_name)
    rule["active"] = True
    get_db().update_rule(rule)
    return jsonify(201)


@app.route("/rule/<rule_name>/deactivate", methods=['PUT'])
def deactivate_rule(rule_name):
    rule = get_db().get_rule(rule_name)
    rule["active"] = False
    get_db().update_rule(rule)
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
    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
        new_structure["resources"] = dict()
        new_structure["resources"][resource] = dict()
        new_structure["resources"][resource][parameter] = value
        get_db().update_structure(new_structure)

    except KeyError:
        abort(404)
    return jsonify(201)


@app.route("/structure/<structure_name>/guard", methods=['PUT'])
def set_structure_to_guarded(structure_name, ):
    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    new_structure["guard"] = True
    get_db().update_structure(new_structure)
    return jsonify(201)


@app.route("/structure/<structure_name>/unguard", methods=['PUT'])
def set_structure_to_unguarded(structure_name):
    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    new_structure["guard"] = False
    get_db().update_structure(new_structure)
    return jsonify(201)


@app.route("/structure/<structure_name>/resources/<resource>/guard", methods=['PUT'])
def set_structure_resource_to_guarded(structure_name, resource):
    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    new_structure["resources"] = dict()
    new_structure["resources"][resource] = dict()
    new_structure["resources"][resource]["guard"] = True
    get_db().update_structure(new_structure)
    return jsonify(201)


def set_structure_multiple_resources_to_guard_state(structure_name, request, state):
    data = request.json
    if not data:
        return abort(400, {"message": "empty content"})
    try:
        resources = data["resources"]
        if not isinstance(resources, (list, str)):
            return abort(400, {"message": "invalid content, resources must be a list or a string"})
        elif isinstance(resources, str):
            resources = [resources]
    except (KeyError, TypeError):
        return abort(400, {"message": "invalid content, must be a json object with resources as key"})

    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    new_structure["resources"] = dict()
    for resource in resources:
        if resource not in ["cpu", "mem", "disk", "net", "energy"]:
            continue
        else:
            new_structure["resources"][resource] = {"guard": state}
    get_db().update_structure(new_structure)
    return jsonify(201)


@app.route("/structure/<structure_name>/resources/guard", methods=['PUT'])
def set_structure_multiple_resources_to_guarded(structure_name):
    return set_structure_multiple_resources_to_guard_state(structure_name, request, True)


@app.route("/structure/<structure_name>/resources/unguard", methods=['PUT'])
def set_structure_multiple_resources_to_unguarded(structure_name):
    return set_structure_multiple_resources_to_guard_state(structure_name, request, False)


@app.route("/structure/<structure_name>/resources/<resource>/unguard", methods=['PUT'])
def set_structure_resource_to_unguarded(structure_name, resource):
    structure = retrieve_structure(structure_name)
    new_structure = MyUtils.copy_structure_base(structure)
    new_structure["resources"] = dict()
    new_structure["resources"][resource] = dict()
    new_structure["resources"][resource]["guard"] = False
    get_db().update_structure(new_structure)
    return jsonify(201)


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
        value = int(request.json["value"])
        if value < 0:
            return abort(400)

        structure_limits["resources"][resource]["boundary"] = value
        get_db().update_limit(structure_limits)
    except KeyError:
        abort(404)
    return jsonify(201)

@app.route("/structure/<structure_name>/profile/<profile_name>", methods=['PUT'])
def set_structure_profile(structure_name, profile_name):
    def __apply_profile_to_container(container):
        for resource in container["resources"]:
            if resource in profile["resources"]:
                container["resources"][resource]["fixed"] = profile["resources"][resource]

    try:
        profile = get_db().get_profile(profile_name)
        structure = get_db().get_structure(structure_name)
    except ValueError:
        return abort(404)

    if structure["subtype"] != "container" and structure["subtype"] != "application":
        return abort(400, {
            "message": "only structures of subtype \'container\' or \'application\' " +
                       "can be used when profiles are applied"})

    if structure["subtype"] == "container":
        __apply_profile_to_container(structure)
        get_db().update_structure(structure)

    if structure["subtype"] == "application":
        for c in structure["containers"]:
            container = get_db().get_structure(c)
            __apply_profile_to_container(container)
            get_db().update_structure(container)

    return jsonify(201)


@app.route("/structure/<structure_name>/guard_policy/serverless", methods=['PUT'])
def set_structure_guard_policy_to_serverless(structure_name):
    try:
        structure = retrieve_structure(structure_name)
        new_structure = MyUtils.copy_structure_base(structure)
        new_structure["guard_policy"] = "serverless"
        get_db().update_structure(new_structure)
    except ValueError:
        return abort(404)
    return jsonify(201)


@app.route("/structure/<structure_name>/guard_policy/fixed", methods=['PUT'])
def set_structure_guard_policy_to_fixed(structure_name):
    try:
        structure = retrieve_structure(structure_name)
        new_structure = MyUtils.copy_structure_base(structure)
        new_structure["guard_policy"] = "fixed"
        get_db().update_structure(new_structure)
    except ValueError:
        return abort(404)
    return jsonify(201)


@app.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

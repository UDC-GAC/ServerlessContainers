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

from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import request
import time

import src.MyUtils.MyUtils as utils
from src.Orchestrator.utils import BACK_OFF_TIME_MS, MAX_TRIES, get_db, get_keys_from_requested_structure, get_resource_keys_from_requested_structure, check_resources_data_is_present, retrieve_structure

users_routes = Blueprint('users', __name__)

USER_KEYS = ["name", "subtype"]


def retrieve_user(user_name):
    try:
        return get_db().get_user(user_name)
    except ValueError:
        return abort(404)


def check_user_exists(user_name):
    try:
        user = get_db().get_user(user_name)
        if user:
            return True
    except ValueError:
        return False
    return False


@users_routes.route("/user/", methods=['GET'])
def get_users():
    return jsonify(get_db().get_users())


@users_routes.route("/user/<user_name>", methods=['GET'])
def get_user(user_name):
    return jsonify(retrieve_user(user_name))


@users_routes.route("/user/<user_name>", methods=['PUT'])
def subscribe_user(user_name):
    req_user = request.json["user"]

    # Check that all the needed data is present on the request
    user = get_keys_from_requested_structure(req_user, USER_KEYS, ["balancing_method"])

    # Check user name in payload and user name in URL are the same
    if user["name"] != user_name:
        return abort(400, {"message": "Name mismatch {0} != {1}".format(user["name"], user_name)})

    # Check if the user already exists
    if check_user_exists(user_name):
        return abort(400, {"message": "User '{0}' already exists".format(user_name)})

    # Check that all the needed data for resources is present on the request
    check_resources_data_is_present(request.json, ["user"])

    # Get data corresponding to user resources
    user["resources"] = {}
    for resource in req_user["resources"]:
        get_resource_keys_from_requested_structure(req_user, user, resource, ["max", "min"])

    user["clusters"] = []

    # Add user to the StateDatabase
    get_db().add_user(user)

    return jsonify(201)


@users_routes.route("/user/clusters/<user_name>/<app_name>", methods=['PUT'])
def subscribe_app_to_user(user_name, app_name):
    user = retrieve_user(user_name)
    app = retrieve_structure(app_name)
    app_name = app["name"]

    # Look for any application that hosts this container, to make sure it is not already subscribed
    users = get_db().get_users()
    for u in users:
        if app_name in u["clusters"]:
            return abort(400, {"message": "Application '{0}' already subscribed to user '{1}'".format(app_name, u["name"])})

    app_changes = {"resources": {}}
    for resource in app["resources"]:
        if resource in user["resources"]:
            try:
                alloc_ratio = app["resources"][resource]["max"] / user["resources"][resource]["max"]
                app["resources"][resource]["alloc_ratio"] = alloc_ratio
                app_changes["resources"][resource] = {"alloc_ratio": alloc_ratio}
            except (ZeroDivisionError, KeyError) as e:
                return abort(400, {"message": "Couldn't set allocation ratio for application '{0}' and "
                                              "user '{1}': {2}".format(app_name, user_name, str(e))})

    user["clusters"].append(app_name)

    get_db().partial_update_structure(app, app_changes)
    get_db().partial_update_user(user, {"clusters": user["clusters"]})
    return jsonify(201)


@users_routes.route("/user/<user_name>", methods=['DELETE'])
def desubscribe_user(user_name):
    user = retrieve_user(user_name)

    # Delete the document for this user
    get_db().delete_user(user)

    return jsonify(201)


@users_routes.route("/user/clusters/<user_name>/<app_name>/", methods=['DELETE'])
def desubscribe_app_from_user(user_name, app_name):
    app = retrieve_structure(app_name)
    user = retrieve_user(user_name)

    app_name = app["name"]
    if app_name not in user["clusters"]:
        return abort(400, {"message": "Application '{0}' missing in user '{1}'".format(app_name, user_name)})
    else:
        user["clusters"].remove(app_name)
        get_db().partial_update_user(user, {"clusters": user["clusters"]})
    return jsonify(201)


@users_routes.route("/user/<user_name>/resources/<resource>/<parameter>", methods=['PUT'])
def set_user_resource_parameter(user_name, resource, parameter):
    # Check resource is valid
    if not utils.valid_resource(resource):
        return abort(400, {"message": "Resource '{0}' is not valid".format(resource)})

    # Check parameter is valid
    valid_parameters = ["max", "min"]
    if parameter not in valid_parameters:
        return abort(400, {"message": "Invalid parameter state"})

    # Try to get the value from the request
    try:
        value = int(request.json["value"])
        if value < 0:
            return abort(400)
    except KeyError:
        return abort(400)

    # Check if user has already set that value
    user = retrieve_user(user_name)
    if user.get("resources", {}).get(resource, {}).get(parameter, -1) == value:
        return jsonify(201)

    # Update the value in the database
    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        user["resources"][resource][parameter] = value
        get_db().partial_update_user(user, {"resources": {resource: {parameter: value}}})

        time.sleep(BACK_OFF_TIME_MS / 1000)
        user = retrieve_user(user_name)
        put_done = user["resources"][resource][parameter] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


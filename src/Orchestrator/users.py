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

from flask import Blueprint, abort
from flask import jsonify
from flask import request
import time

from src.Orchestrator.utils import BACK_OFF_TIME_MS, MAX_TRIES, get_db

users_routes = Blueprint('users', __name__)


def retrieve_user(user_name):
    try:
        return get_db().get_user(user_name)
    except ValueError:
        abort(404, "user does not exist")


@users_routes.route("/user/", methods=['GET'])
def get_users():
    return jsonify(get_db().get_users())


@users_routes.route("/user/<user_name>", methods=['GET'])
def get_user(user_name):
    return jsonify(retrieve_user(user_name))


@users_routes.route("/user/<user_name>/accounting/<key>", methods=['GET'])
def get_accounting_value(user_name, key):
    user = retrieve_user(user_name)
    return jsonify(user["accounting"][key])


@users_routes.route("/user/<user_name>/accounting/<key>", methods=['PUT'])
def set_accounting_value(user_name, key):
    data = request.json
    if not data:
        abort(400, "empty content")

    value = request.json["value"]

    if not isinstance(value, (int, str)):
        abort(400, "invalid content, resources must be a number or a string")
    elif value in ["greedy", "conservative", "used", "current"]:
        pass
    elif value == "true" or value == "false":
        value = value == "true"
    else:
        try:
            value = float(value)
        except ValueError:
            abort(400, "invalid content, not bool, policy, billing type, int, or float")

    user = retrieve_user(user_name)
    try:
        bogus = user["accounting"][key]
    except KeyError:
        abort(404, "User does not have accounting initialized")

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        user["accounting"][key] = value
        get_db().update_user(user)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        user = retrieve_user(user_name)
        put_done = user["accounting"][key] == value

        if tries >= MAX_TRIES:
            abort(400, "MAX_TRIES updating database document")

    return jsonify(201)


@users_routes.route("/user/<user_name>", methods=['PUT'])
def subscribe_user(user_name):
    req_user = request.json

    # Check that all the needed data is present on the request
    user = {}
    for key in ["name"]:
        if key not in req_user:
            abort(400, "Missing key '{0}'".format(key))
        else:
            user[key] = req_user[key]

    if user["name"] != user_name:
        abort(400, "Name mismatch".format(key))

    # Check if the user already exists
    try:
        user = get_db().get_user(user_name)
        if user:
            abort(400, "User with this name already exists".format(key))
    except ValueError:
        pass

    if "applications" in req_user:
        for app in req_user["applications"]:
            try:
                get_db().get_structure(app)
            except ValueError:
                abort(400, "The application '{0}', which allegedly is a part of this user, does not exist".format(app))
        user["applications"] = req_user["applications"]
    else:
        user["applications"] = list()

    # All looks good up to this point
    user["type"] = "user"

    # Initialize accounting
    user["accounting"] = {
        "active": True,
        "restricted": False,
        "pending": 0,
        "credit": 0,
        "coins": 0,
        "min_balance": 2,
        "max_debt": -2,
        "policy": "greedy",  # conservative
        "billing_type": "used" # current
    }

    get_db().add_user(user)

    return jsonify(201)


@users_routes.route("/user/<user_name>", methods=['DELETE'])
def desubscribe_user(user_name):
    user = retrieve_user(user_name)

    # Delete the document for this user
    get_db().delete_user(user)

    return jsonify(201)


@users_routes.route("/user/<user_name>/energy/max", methods=['PUT'])
def set_user_energy_max(user_name):
    user = retrieve_user(user_name)
    try:
        bogus = user["energy"]["max"]
    except KeyError:
        abort(404, "User does not have energy initialized")

    value = int(request.json["value"])
    if value < 0:
        abort(400, "Invalid value for max energy")

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        user["energy"]["max"] = value
        get_db().update_user(user)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        user = retrieve_user(user_name)
        put_done = user["energy"]["max"] == value

        if tries >= MAX_TRIES:
            abort(400, "MAX_TRIES updating database document")

    return jsonify(201)

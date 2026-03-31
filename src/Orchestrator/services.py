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

from src.Orchestrator.utils import BACK_OFF_TIME_MS, MAX_TRIES, get_db

service_routes = Blueprint('services', __name__)

STR_KEYS = {
    "STRUCTURE_GUARDED", "ENERGY_MODEL_NAME", "ENERGY_MODEL_RELIABILITY",   # Guardian
    "CONTAINERS_SCOPE", "BALANCING_METHOD", "BALANCING_POLICY",             # ReBalancer
    "CONTROL_POLICY", "POWER_MODEL", "EVENTS_SYSTEM"                        # EnergyController
}
BOOL_VALUES = {"true", "false"}


def retrieve_service(service_name):
    try:
        return get_db().get_service(service_name)
    except ValueError:
        return abort(404)


def coerce_value(value):
    # Boolean strings are coerced to bool
    if value in BOOL_VALUES:
        return value == "true"
    # Numeric strings are coerced to int or float
    if 0 < float(value) < 1:
        return float(value)
    else:
        return int(value)


@service_routes.route("/service/", methods=['GET'])
def get_services():
    return jsonify(get_db().get_services())


@service_routes.route("/service/<service_name>", methods=['GET'])
def get_service(service_name):
    return jsonify(retrieve_service(service_name))


@service_routes.route("/service/<service_name>", methods=['PUT'])
def set_service_information(service_name):
    data = request.json
    service = retrieve_service(service_name)
    put_done = False
    tries = 0
    changes = {"config": {}}
    while not put_done:
        tries += 1
        for key in data:
            service["config"][key] = data[key]
            changes["config"][key] = data[key]
        get_db().partial_update_service(service, changes)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        put_done = True
        service = retrieve_service(service_name)
        for key in data:
            put_done = put_done and service["config"][key] == data[key]

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


@service_routes.route("/service/<service_name>/<key>", methods=['PUT'])
def set_service_value(service_name, key):
    put_done = False
    tries = 0

    data = request.json
    if not data:
        abort(400, {"message": "empty content"})

    value = request.json["value"]

    if not isinstance(value, (list, str)):
        abort(400, {"message": "invalid content, resources must be a list or a string"})

    if isinstance(value, str) and key not in STR_KEYS:
        try:
            value = coerce_value(value)
        except ValueError:
            return abort(400, {"message": "bad content"})

    # Check if it is really needed to carry out the operation
    service = retrieve_service(service_name)
    if key in service["config"] and service["config"][key] == value:
        put_done = True

    while not put_done:
        tries += 1
        service["config"][key] = value
        get_db().partial_update_service(service, {"config": {key: value}})

        time.sleep(BACK_OFF_TIME_MS / 1000)
        service = retrieve_service(service_name)
        put_done = service["config"][key] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


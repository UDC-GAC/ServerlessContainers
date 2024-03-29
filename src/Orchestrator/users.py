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

users_routes = Blueprint('users', __name__)

@users_routes.route("/user/", methods=['GET'])
def get_users():
    return jsonify(get_db().get_users())


@users_routes.route("/user/<user_name>", methods=['GET'])
def get_user(user_name):
    return jsonify(get_db().get_user(user_name))


@users_routes.route("/user/<user_name>/energy/max", methods=['PUT'])
def set_user_energy_max(user_name):
    user = get_db().get_user(user_name)
    try:
        bogus = user["energy"]["max"]
    except KeyError:
        abort(404)

    value = int(request.json["value"])
    if value < 0:
        return abort(400)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        user["energy"]["max"] = value
        get_db().update_user(user)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        user = get_db().get_user(user_name)
        put_done = user["energy"]["max"] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)

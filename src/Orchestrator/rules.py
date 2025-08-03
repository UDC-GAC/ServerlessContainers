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

rules_routes = Blueprint('rules', __name__)

SUPPORTED_POLICIES = {
    "up": ["amount", "proportional", "modelling", "fixed-ratio"],
    "down": ["amount", "proportional", "modelling", "fixed-ratio", "fit_to_usage"]
}


def retrieve_rule(rule_name):
    try:
        return get_db().get_rule(rule_name)
    except ValueError:
        return abort(404)


@rules_routes.route("/rule/<rule_name>", methods=['GET'])
def get_rule(rule_name):
    return jsonify(retrieve_rule(rule_name))


@rules_routes.route("/rule/", methods=['GET'])
def get_rules():
    return jsonify(get_db().get_rules())


@rules_routes.route("/rule/<rule_name>/activate", methods=['PUT'])
def activate_rule(rule_name):
    rule = retrieve_rule(rule_name)
    put_done = rule["active"]

    tries = 0
    while not put_done:
        tries += 1
        rule["active"] = True
        get_db().update_rule(rule)
        rule = retrieve_rule(rule_name)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        put_done = rule["active"]
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@rules_routes.route("/rule/<rule_name>/deactivate", methods=['PUT'])
def deactivate_rule(rule_name):
    rule = retrieve_rule(rule_name)
    put_done = not rule["active"]

    tries = 0
    while not put_done:
        tries += 1
        rule["active"] = False
        get_db().update_rule(rule)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        rule = retrieve_rule(rule_name)
        put_done = not rule["active"]
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@rules_routes.route("/rule/<rule_name>/amount", methods=['PUT'])
def change_amount_rule(rule_name):
    rule = retrieve_rule(rule_name)

    if rule["generates"] != "requests" or rule["rescale_type"] != "up":
        return abort(400, {"message": "This rule can't have its amount changed"})

    try:
        amount = int(request.json["value"])
    except KeyError:
        return abort(400)

    rule = retrieve_rule(rule_name)
    put_done = rule["amount"] == amount

    tries = 0
    while not put_done:
        tries += 1
        rule["amount"] = amount
        get_db().update_rule(rule)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        rule = retrieve_rule(rule_name)
        put_done = rule["amount"] == amount
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)


@rules_routes.route("/rule/<rule_name>/policy", methods=['PUT'])
def change_policy_rule(rule_name):
    rule = retrieve_rule(rule_name)

    if rule["generates"] != "requests":
        return abort(400, {"message": "This rule can't have its policy changed"})

    rescale_policy = request.json["value"]
    if rescale_policy not in SUPPORTED_POLICIES[rule["rescale_type"]]:
        return abort(400, {"message": f"Invalid policy for a rescale {rule['rescale_type']} rule"})

    put_done = rule["rescale_policy"] == rescale_policy
    tries = 0
    while not put_done:
        tries += 1
        rule["rescale_policy"] = rescale_policy
        get_db().update_rule(rule)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        rule = retrieve_rule(rule_name)
        put_done = rule["rescale_policy"] == rescale_policy
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)


@rules_routes.route("/rule/<rule_name>/events_required", methods=['PUT'])
def change_event_up_amount(rule_name):
    try:
        new_amount = int(request.json["value"])
        if new_amount < 0:
            return abort(400, {"message": "Invalid amount, only 0 or greater are valid"})

        event_type = request.json["event_type"]
        if event_type not in ["down", "up"]:
            return abort(400, {"message": "Invalid type of event, only 'up' or 'down' accepted"})
    except KeyError:
        return abort(400, {"message": "Invalid amount"})

    rule = retrieve_rule(rule_name)
    if rule["rescale_type"] not in ["down", "up"]:
        return abort(400, {"message": "Can't apply this change to this rule"})

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        correct_key = None
        list_rules_entry = 0
        for part in rule["rule"]["and"]:
            # Get the first and only value from the dictionary
            operator, expr = next(iter(part.items()))  # e.g., {"<=": [{"var": "events.scale.up"}, 1]}
            rule_var = expr[0]["var"]

            if event_type == "up" and rule_var == "events.scale.up":
                rule["rule"]["and"][list_rules_entry][operator][1] = new_amount
                rule["events_to_remove"] = new_amount
                correct_key = operator
                break

            if event_type == "down" and rule_var == "events.scale.down":
                rule["rule"]["and"][list_rules_entry][operator][1] = new_amount
                rule["events_to_remove"] = new_amount
                correct_key = operator
                break
            list_rules_entry += 1

        get_db().update_rule(rule)

        time.sleep(BACK_OFF_TIME_MS / 1000)

        rule = retrieve_rule(rule_name)
        put_done = rule["rule"]["and"][list_rules_entry][correct_key][1] == new_amount
        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})
    return jsonify(201)

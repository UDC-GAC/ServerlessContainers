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

from flask import abort
from flask import g
from datetime import datetime, timezone
import os
import time
import yaml

import src.StateDatabase.couchdb as couchdb

MANDATORY_RESOURCES = {"cpu", "mem"}
MAX_TRIES = 10
BACK_OFF_TIME_MS = 500
COUCHDB_URL = os.getenv('COUCHDB_URL')
if not COUCHDB_URL:
    COUCHDB_URL = "couchdb"

# Services that can scale the containers (SCALING_SERVICE in services_config.yml), the first one by default
SCALING_SERVICES = ("scaler", "energy_manager")
_scaling_service = {"mtime": None, "value": SCALING_SERVICES[0]}


def get_db():
    global COUCHDB_URL
    """Opens a new database connection if there is none yet for the current application context."""
    if not hasattr(g, 'db_handler'):
        #g.db_handler = couchDB.CouchDBServer(couchdb_url=COUCHDB_URL)
        g.db_handler = couchdb.CouchDBServer()
    return g.db_handler


def get_scaling_service():
    """Service that scales the containers: SCALING_SERVICE in services_config.yml, read again when the file changes."""
    path = os.path.join(os.environ.get("SERVERLESS_PATH", "."), "services_config.yml")
    try:
        mtime = os.path.getmtime(path)
        if mtime != _scaling_service["mtime"]:
            with open(path, "r") as f:
                value = (yaml.safe_load(f) or {}).get("SCALING_SERVICE", SCALING_SERVICES[0])
            if value not in SCALING_SERVICES:
                print("[{0}] Unknown SCALING_SERVICE '{1}' in {2} ({3}), using '{4}'".format(
                    datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S%z'), value, path,
                    ", ".join(SCALING_SERVICES), SCALING_SERVICES[0]), flush=True)
                value = SCALING_SERVICES[0]
            _scaling_service.update(mtime=mtime, value=value)
    except (OSError, yaml.YAMLError):
        pass
    return _scaling_service["value"]


def energy_manager_scales():
    return get_scaling_service() == "energy_manager"


def notify_energy_manager():
    """Ask the EnergyManager (if it exists) to reload its state from CouchDB in its next iteration (~1 s)."""
    if not energy_manager_scales():
        return
    try:
        service = get_db().get_service("energy_manager")
        get_db().partial_update_service(service, {"config": {"STATE_UPDATE": int(time.time() * 1000)}})
    except Exception:
        pass


def retrieve_structure(structure_name):
    try:
        return get_db().get_structure(structure_name)
    except ValueError:
        return abort(404)


def get_keys_from_requested_structure(req_structure, mandatory_keys, optional_keys=[]):
    structure = {}
    for key in mandatory_keys:
        if key not in req_structure:
            return abort(400, {"message": "Missing key '{0}'".format(key)})
        else:
            structure[key] = req_structure[key]

    for key in optional_keys:
        if key in req_structure:
            structure[key] = req_structure[key]

    structure["type"] = "structure"

    return structure


def get_resource_keys_from_requested_structure(req_structure, structure, resource, mandatory_keys, optional_keys=[]):
    structure["resources"][resource] = {}
    for key in mandatory_keys:
        if key not in req_structure["resources"][resource]:
            return abort(400, {"message": "Missing key '{0}' for '{1}' resource".format(key, resource)})
        else:
            structure["resources"][resource][key] = req_structure["resources"][resource][key]

    for key in optional_keys:
        if key in req_structure["resources"][resource]:
            structure["resources"][resource][key] = req_structure["resources"][resource][key]


def check_resources_data_is_present(data, res_info_type=None):
    for res_info in res_info_type:
        if "resources" not in data[res_info]:
            return abort(400, {"message": "Missing resource {0} information".format(res_info)})
        for resource in MANDATORY_RESOURCES:
            if resource not in data[res_info]["resources"]:
                return abort(400, {"message": "Missing '{0}' {1} resource information".format(resource, res_info)})

        if "disk" in data[res_info]["resources"] and ("disk_read" not in data[res_info]["resources"] or "disk_write" not in data[res_info]["resources"]):
            return abort(400, {"message": "Missing disk read or write bandwidth for structure {0}".format(data[res_info])})


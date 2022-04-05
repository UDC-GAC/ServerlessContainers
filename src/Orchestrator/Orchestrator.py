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


import json

import argparse
from flask import Flask
from flask import Response
from src.Orchestrator.rules import rules_routes
from src.Orchestrator.services import service_routes
from src.Orchestrator.structures import structure_routes
from src.Orchestrator.users import users_routes

app = Flask(__name__)

app.register_blueprint(rules_routes)
app.register_blueprint(service_routes)
app.register_blueprint(structure_routes)
app.register_blueprint(users_routes)


@app.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Ochestrator REST service to automatically change configuration on the CouchDb rescaling database')
    parser.add_argument('--database_url_string', type=str, default="couchdb",
                        help="The hostname that hosts the rescaling couchDB")
    args = parser.parse_args()
    if args.database_url_string:
        COUCHDB_URL = args.database_url_string

    app.run(host='0.0.0.0', port=5000)

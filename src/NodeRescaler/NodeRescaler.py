# Copyright (c) 2019 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
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

from flask import Flask
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
from werkzeug.serving import WSGIRequestHandler

from src.NodeRescaler.lxd_node_resource_manager import LXDContainerManager
from functools import wraps

node_resource_manager = None

node_rescaler = Flask(__name__)


def initialize_LXD(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        global node_resource_manager
        if not node_resource_manager:
            node_resource_manager = LXDContainerManager()
            if not node_resource_manager:
                raise Exception("Could not instantiate LXD Manager")
        else:
            pass
        return f(*args, **kwargs)

    return wrap


@node_rescaler.route("/container/", methods=['GET'])
@initialize_LXD
def get_containers_resources():
    try:
        container_name = request.form['name']
    except KeyError:
        container_name = request.args.get('name')

    if container_name is not None:
        return jsonify(node_resource_manager.get_node_resources_by_name(container_name))
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@node_rescaler.route("/container/<container_name>", methods=['PUT'])
@initialize_LXD
def set_container_resources(container_name):
    if container_name != "":
        success, applied_config = node_resource_manager.set_node_resources(container_name, request.json)
        if not success:
            # TODO Improve the failure detection, filter out which set process failed and report it
            return Response(json.dumps(applied_config), status=500, mimetype='application/json')
        else:
            applied_config = node_resource_manager.get_node_resources_by_name(container_name)
            if applied_config is not None:
                return Response(json.dumps(applied_config), status=201, mimetype='application/json')
            else:
                return abort(404)
    else:
        abort(400)


@node_rescaler.route("/container/<container_name>", methods=['GET'])
@initialize_LXD
def get_container_resources(container_name):
    if container_name != "":
        data = node_resource_manager.get_node_resources_by_name(container_name)
        if data is not None:
            return jsonify(data)
        else:
            return abort(404)
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@node_rescaler.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":
    node_resource_manager = LXDContainerManager()
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    node_rescaler.run(host='0.0.0.0', port=8000)

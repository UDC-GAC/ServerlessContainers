#!/usr/bin/python
import json

from flask import Flask
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
from werkzeug.serving import WSGIRequestHandler

import lxd_node_resource_manager as node_resource_manager

app = Flask(__name__)


@app.route("/container/", methods=['GET'])
def get_containers_resources():
    try:
        container_name = request.form['name']
    except KeyError:
        container_name = request.args.get('name')

    if container_name is not None:
        return jsonify(node_resource_manager.get_node_resources(container_name))
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@app.route("/container/<container_name>", methods=['PUT'])
def set_container_resources(container_name):
    if container_name != "":
        success, applied_config = node_resource_manager.set_node_resources(container_name, request.json)
        if not success:
            # TODO Improve the failure detection, filter out which set process failed and report it
            return Response(json.dumps(applied_config), status=500, mimetype='application/json')
        else:
            applied_config = node_resource_manager.get_node_resources(container_name)
            if applied_config is not None:
                return Response(json.dumps(applied_config), status=201, mimetype='application/json')
            else:
                return abort(404)
    else:
        abort(400)


@app.route("/container/<container_name>", methods=['GET'])
def get_container_resources(container_name):
    if container_name != "":
        data = node_resource_manager.get_node_resources(container_name)
        if data is not None:
            return jsonify(data)
        else:
            return abort(404)
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@app.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(host='0.0.0.0', port=8000)

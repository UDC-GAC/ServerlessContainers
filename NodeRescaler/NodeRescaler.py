from flask import Flask
from flask_cors import CORS, cross_origin
from flask import request
from flask import jsonify
from flask import abort
from flask import Response
import json 
import time
import sys

sys.path.append('..')
import NodeManager.lxd_node_resource_manager as NodeResourceManager

app = Flask(__name__)


@app.route("/container/", methods=['GET'])
def get_containers_resources():
	
	try:
		try:
			container_name = request.form['name']
		except KeyError:
			container_name = request.args.get('name')
	except Exception:
		pass
	  
	if container_name != None:
		return jsonify(NodeResourceManager.get_node_resources(container_name))
	else:
		return jsonify(NodeResourceManager.get_all_nodes())


@app.route("/container/<container_name>", methods=['PUT'])
def set_container_resources(container_name):
	if container_name != "":
		success, applied_config = NodeResourceManager.set_node_resources(container_name, request.json)
		if not success:
			return Response(json.dumps(applied_config), status=500, mimetype='application/json')
		else:				
			applied_config = NodeResourceManager.get_node_resources(container_name)
			if applied_config != None:
				return Response(json.dumps(applied_config), status=201, mimetype='application/json')
			else:
				return abort(404)
	else:
		abort(400)


@app.route("/container/<container_name>", methods=['GET'])
def get_container_resources(container_name):
	
	if container_name != "":
		data = NodeResourceManager.get_node_resources(container_name)
		if data != None:
			return jsonify(data)
		else:
			return abort(404)
	else:
		return jsonify(NodeResourceManager.get_all_nodes())


@app.route("/heartbeat", methods=['GET'])
def heartbeat():
	return Response(json.dumps({"status":"alive"}), status=200, mimetype='application/json')
	
if __name__ == "__main__":
	app.run(host='0.0.0.0', port=8000)



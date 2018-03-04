from flask import Flask
from flask_cors import CORS, cross_origin
from flask import request
from flask import jsonify
from flask import abort
from flask import Response
import json 
import time

import node_resource_manager as NodeResourceManager

app = Flask(__name__)
#CORS(app)

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
		if not NodeResourceManager.set_node_resources(container_name, request.json):
			return abort(500)
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


if __name__ == "__main__":
	app.run()



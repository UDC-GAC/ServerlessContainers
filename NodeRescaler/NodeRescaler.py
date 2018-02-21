from flask import Flask
from flask_cors import CORS, cross_origin
from flask import request
from flask import jsonify
from flask import abort
import json 

import node_resource_manager as NodeResourceManager

app = Flask(__name__)
#CORS(app)

@app.route("/container/", methods=['GET'])
def get_container_resources():
	container_name = None
	
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

if __name__ == "__main__":
	app.run()



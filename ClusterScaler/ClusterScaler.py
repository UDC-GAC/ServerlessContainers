#/usr/bin/python
import requests
import json
import re
import time
import sys

sys.path.append('../StateDatabase')
import couchDB

database_handler = couchDB.CouchDBServer()


default_config = {"POLLING_FREQUENCY":10, "REQUEST_TIMEOUT":600}

def get_config_value(config, key):
	try:
		return config["scaler_config"][key]
	except KeyError:
		return default_config[key]
		
		
def filter_requests(request_timeout):
	filtered_requests = list()
	merged_requests = list()
	all_requests = database_handler.get_requests()
	
	# First purge the old requests
	for request in all_requests:
		if request["timestamp"] < time.time() - request_timeout:
			database_handler.delete_request(request)
		else:
			filtered_requests.append(request)
	
	# Then remove repeated requests for the same structure if found
	structure_requests_dict = dict()
	for request in filtered_requests:
		structure = request["structure"] # The structure name (string), acting as an id
		action = request["action"] # The action name (string)
		if structure in structure_requests_dict and action in structure_requests_dict[structure]:
			# A previouse request was found for this structure, remove old one and leave the newer one
			stored_request = structure_requests_dict[structure][action]
			if stored_request["timestamp"] > request["timestamp"]:
				# The stored request is newer, leave it and remove the retrieved one
				database_handler.delete_request(request)
			else:
				# The stored request is older, remove it and save the retrieved one
				database_handler.delete_request(stored_request)
				structure_requests_dict[structure][action] = request
		else:
			if not structure in structure_requests_dict:
				structure_requests_dict[structure] = dict()
			structure_requests_dict[structure][action] = request
	
	for structure in structure_requests_dict:
		for action in structure_requests_dict[structure]:
			merged_requests.append(structure_requests_dict[structure][action])

	return merged_requests

def scale():
	while True:
		config = database_handler.get_all_database_docs("config")[0] #FIX
		polling_frequency = get_config_value(config, "POLLING_FREQUENCY")
		request_timeout = get_config_value(config, "REQUEST_TIMEOUT")
		
		requests = filter_requests(request_timeout)
		if not requests:
			# No requests to process
			print("No requests at " + time.strftime("%D %H:%M:%S", time.localtime()))
		else:
			print("Requests at " + time.strftime("%D %H:%M:%S", time.localtime()))
			for request in requests:	
				print json.dumps(request)
			print 
				
		time.sleep(polling_frequency)

scale()

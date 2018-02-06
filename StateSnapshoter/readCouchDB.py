#/usr/bin/python
import requests
import json
import sys
import time

sys.path.append('../StateDatabase')
import couchDB

def translate_doc_to_timeseries(doc):
	node_name = doc["node"]
	timestamp=int(time.time())
	
	for resource in doc["resources"]:
		for boundary in doc["resources"][resource]:
			value = doc["resources"][resource][boundary]
			metric = doc["type"] + "." + resource + "." + boundary
			timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=node_name))
			print json.dumps(timeseries)


database_handler = couchDB.CouchDBServer()
while(True):
	for limit in database_handler.get_all_database_docs("limits"):
		translate_doc_to_timeseries(limit)
	for node in database_handler.get_all_database_docs("nodes"):
		translate_doc_to_timeseries(node)
	time.sleep(10)



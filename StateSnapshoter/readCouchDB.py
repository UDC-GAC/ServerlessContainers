#/usr/bin/python
from __future__ import print_function
import requests
import json
import sys
import time
import traceback

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

sys.path.append('../StateDatabase')
import couchDB

def translate_doc_to_timeseries(doc):
	try:
		try:
			node_name = doc["name"]
		except KeyError:
			node_name = doc["structure"]
		timestamp=int(time.time())
		
		for resource in doc["resources"]:
			for boundary in doc["resources"][resource]:
				value = doc["resources"][resource][boundary]
				metric = doc["type"] + "." + resource + "." + boundary
				timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=node_name))
				print(json.dumps(timeseries))
	except Exception as e:
		eprint("Error with document: " + str(doc))
		traceback.print_exc()

database_handler = couchDB.CouchDBServer()
while(True):
	for limit in database_handler.get_all_database_docs("limits"):
		translate_doc_to_timeseries(limit)
	for structure in database_handler.get_all_database_docs("structures"):
		translate_doc_to_timeseries(structure)
	time.sleep(10)



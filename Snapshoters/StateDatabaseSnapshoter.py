#/usr/bin/python
from __future__ import print_function
import requests
import json
import sys
import time
import traceback

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)




sys.path.append('..')
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as utils


sys.path.append('../../metrics-to-time-series/pipes')
import pipes.send_to_OpenTSDB as OpenTSDB_sender


def translate_doc_to_timeseries(doc):
	try:
		try:
			node_name = doc["name"]
		except KeyError:
			node_name = doc["structure"]
		timestamp=int(time.time())
		
		timeseries_list = list()
		for resource in doc["resources"]:
			for boundary in doc["resources"][resource]:
				value = doc["resources"][resource][boundary]
				metric = doc["type"] + "." + resource + "." + boundary
				timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=node_name))
				timeseries_list.append(timeseries)
		return timeseries_list
	except Exception as e:
		eprint("Error with document: " + str(doc))
		traceback.print_exc()

db = couchDB.CouchDBServer()

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY":10}
SERVICE_NAME = "database_snapshoter"

while(True):
	service = db.get_service(SERVICE_NAME)

	utils.beat(db, SERVICE_NAME)

	# CONFIG
	config = service["config"]
	polling_frequency = utils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
	
	docs = []
	for limit in db.get_all_database_docs("limits"):
		docs += translate_doc_to_timeseries(limit)
	for structure in db.get_structures(subtype="container"):
		docs += translate_doc_to_timeseries(structure)
	
	success = OpenTSDB_sender.send_json_documents(docs)
	if not success:
		eprint("[TSDB SENDER] couldn't properly post documents")
	else:
		print ("Post was done at: " +  time.strftime("%D %H:%M:%S", time.localtime()) + " with " + str(len(docs)) + " documents")

	time.sleep(polling_frequency)



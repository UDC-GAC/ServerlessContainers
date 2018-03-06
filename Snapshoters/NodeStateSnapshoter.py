#/usr/bin/python
from __future__ import print_function
import requests
import json
import sys
import time
import traceback

sys.path.append('../StateDatabase')
import couchDB

database_handler = couchDB.CouchDBServer()

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)


def get_container_resources(container_name):
	r = requests.get("http://dante:8000/container/"+container_name, headers = {'Accept':'application/json'})
	if r.status_code == 200:
		return dict(r.json())
	else:
		return None


translate_map = {
		"cpu": {"metric":"structure.cpu.current", "limit_label":"effective_cpu_limit"}, 
		"mem": {"metric":"structure.mem.current", "limit_label":"mem_limit"}
		}


def generate_timeseries(container_name, resources):
	
	try:
		timestamp=int(time.time())
		
		for resource in resources:
			if resource == "disks":
				continue
			if resource == "networks":
				continue
		
			value = resources[resource][translate_map[resource]["limit_label"]]
			metric = translate_map[resource]["metric"]
			timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags=dict(host=container_name))
			
			print(json.dumps(timeseries))
							
	except Exception as e:
		eprint("Error with container data of: " + str(container_name) + " with resources: " + str(resources))
		traceback.print_exc()

def update_container_current_values(container_name, resources):
	try:
		timestamp=int(time.time())
		updated_structure = database_handler.get_structure(container_name)
		
		for resource in resources:
			if resource == "disks":
				continue
			if resource == "networks":
				continue
		
		
			updated_structure["resources"][resource]["current"] = resources[resource][translate_map[resource]["limit_label"]]
		
		print ("Success with container : " + str(container_name) + " at time: " + time.strftime("%D %H:%M:%S", time.localtime()))
		database_handler.update_doc("structures", updated_structure)
							
	except Exception as e:
		eprint("Error with container data of: " + str(container_name) + " with resources: " + str(resources))
		traceback.print_exc()
		
	

while(True):
	containers = ["node0","node1","node2","node3"]
	#containers = ["node0"]
	for container_name in containers:
		resources = get_container_resources(container_name)
		
		# Persist by updating the Database current value and letting the DatabaseSnapshoter update the value
		update_container_current_values(container_name, resources)
		
		# Persist through timeseries sent to OpenTSDB
		#generate_timeseries(container_name, resources)
			
	time.sleep(10)



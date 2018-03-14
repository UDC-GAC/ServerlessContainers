#/usr/bin/python
from __future__ import print_function
import time
import logging
import sys
import requests

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)
	
def beat(db, service_name):
	service = db.get_service(service_name)
	service["heartbeat_human"] =  time.strftime("%D %H:%M:%S", time.localtime())
	service["heartbeat"] =  time.time()
	db.update_doc("services", service)


def get_config_value(config, default_config, key):
	try:
		return config[key]
	except KeyError:
		return default_config[key]

def logging_info(message, debug=True):
	logging.info(message)
	if debug: print("INFO: " + message)

def logging_warning(message, debug=True):
	logging.warning(message)
	if debug: print("WARN: " +message)

def logging_error(message, debug=True):
	logging.error(message)
	if debug: eprint("ERROR: " + message)

def get_time_now_string():
	 return str(time.strftime("%D %H:%M:%S", time.localtime()))

def get_container_resources(container_name):
	r = requests.get("http://dante:8000/container/"+container_name, headers = {'Accept':'application/json'})
	if r.status_code == 200:
		return dict(r.json())
	else:
		return None


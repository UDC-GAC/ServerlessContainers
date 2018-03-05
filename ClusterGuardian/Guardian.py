#/usr/bin/python
import requests
import json
import re
import time
import sys
import traceback

sys.path.append('../StateDatabase')
import couchDB

from json_logic import jsonLogic

class BDWatchdog:
	
	OPENTSDB_URL = "opentsdb"
	OPENTSDB_PORT = 4242
	
	def __init__(self, server = 'http://'+ OPENTSDB_URL + ':' + str(int(OPENTSDB_PORT))):
		if self.check_valid_url(server):
			self.server = server
		else:
			raise ValueError("Invalid server url %s", server)

	def check_valid_url(self, url):
		return True
	
	def get_points(self, query):
		r = requests.post(self.server + "/api/query", data=json.dumps(query), headers = {'content-type': 'application/json','Accept':'application/json'})
		if r.status_code == 200:
			return json.loads(r.text)
		else:
			r.raise_for_status()
		

monitoring_handler = BDWatchdog()
database_handler = couchDB.CouchDBServer()
METRICS = ['proc.cpu.user', 'proc.mem.resident', 'proc.cpu.kernel', 'proc.mem.virtual']
RESOURCES = ['cpu','mem','disk','net']
########################

NO_METRIC_DATA_DEFAULT_VALUE = -1
## GET THESE VARIABLES FROM STATE DATABASE

def get_structure_usages(structure, window_difference, window_delay):
	usages = dict()
	subquery = list()
	for metric in METRICS:
		usages[metric] = NO_METRIC_DATA_DEFAULT_VALUE
		subquery.append(dict(aggregator='sum', metric=metric, tags=dict(host=structure["name"])))
		

	start = int(time.time() - (window_difference + window_delay))
	end = int(time.time() - window_delay)
	query = dict(start=start, end=end, queries=subquery)
	result = monitoring_handler.get_points(query)
	
	for metric in result:
		dps = metric["dps"]
		summatory = sum(dps.values())
		if len(dps) > 0:
			average_real = summatory / len(dps)
		else:
			average_real = 0
		usages[metric["metric"]] = average_real
		
	return usages


def filter_and_purge_old_events(structure, event_timeout):
	structure_events = database_handler.get_events(structure)
	filtered_events = list()
	for event in structure_events:
		if event["timestamp"] < time.time() - event_timeout:
			# Event is too old, remove it
			database_handler.delete_event(event)
		else:
			# Event is not too old, keep it
			filtered_events.append(event)
	return filtered_events

def reduce_structure_events(structure_events):
	#structure_events = database_handler.get_events(structure)
	events_reduced = {"action": {}}
	for resource in RESOURCES:
		events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up":0}}}
		
	for event in structure_events:
		key = event["action"]["events"]["scale"].keys()[0]
		value = event["action"]["events"]["scale"][key]
		events_reduced["action"][event["resource"]]["events"]["scale"][key] += value
	return events_reduced["action"]


def generateEventName(event, resource):
	finalString= "none"
	if "down" in event["scale"].keys() and event["scale"]["down"] > 0:
		finalString = resource.title() + "Underuse"
	if "up" in event["scale"].keys() and event["scale"]["up"] > 0: 
		finalString = resource.title() + "Bottleneck"
	return finalString


def match_container_limits(structure, usages, resources, limits, rules):
	events = []
	data = {}
	
	for resource in RESOURCES:
		data[resource] = dict()
		data[resource]["proc"] = {}
		data[resource]["limits"] = {}
		data[resource]["structure"] = {}
		data[resource]["proc"][resource] = dict()
		data[resource]["limits"][resource] = limits[resource]
		data[resource]["structure"][resource] = resources[resource]
	
	
	for usage_metric in usages:
		keys = usage_metric.split(".")
		data[keys[1]][keys[0]][keys[1]][keys[2]] = usages[usage_metric]	
	
	for rule in rules:
		if rule["generates"] == "events":
			if(jsonLogic(rule["rule"], data[rule["resource"]])):
				events.append(dict(
						name=generateEventName(rule["action"]["events"], rule["resource"]),
						resource=rule["resource"],
						type="event", 
						structure=structure["name"], 
						action=rule["action"], 
						timestamp=int(time.time()))
					)
	return events

def process_events(events):
	for event in events:
		database_handler.add_doc("events", event)

def process_requests(requests):
	for request in requests:
		database_handler.add_doc("requests", request)


def match_structure_events(structure, events, rules):
	requests = []
	data = events
	for rule in rules:
		if rule["generates"] == "requests":
			if(jsonLogic(rule["rule"], data[rule["resource"]])):
				requests.append(dict(
					type="request",
					resource=rule["resource"],
					amount=rule["amount"],
					structure=structure["name"], 
					action=rule["action"]["requests"][0], 
					timestamp=int(time.time()))
				)
				database_handler.delete_num_events_by_structure(structure, generateEventName(data[rule["resource"]]["events"], rule["resource"]), rule["events_to_remove"])
	return requests


default_config = {"WINDOW_TIMELAPSE":10, "WINDOW_DELAY":10, "EVENT_TIMEOUT":40}


def get_config_value(config, key):
	try:
		return config["guardian_config"][key]
	except KeyError:
		return default_config[key]


def try_get_value(dict, key):
	try:
		#return str("%.2f" % dict[key]) # Float with 2 decimals
		return int(dict[key])
	except KeyError:
		return "n/a"

def print_container_status(resource_label, resources_dict, limits_dict, usages_dict):
	translator_dict = {"cpu": "proc.cpu.user", "mem":"proc.mem.resident"}
	if usages_dict[translator_dict[resource_label]] == -1 : 
		usage_value_string = "n/a"
	else:
		usage_value_string = str("%.2f" % usages_dict[translator_dict[resource_label]])
			
			
	return 	\
		(str(try_get_value(resources_dict[resource_label], "max"))+","+ \
		str(try_get_value(resources_dict[resource_label], "current"))+","+ \
		str(try_get_value(limits_dict[resource_label], "upper"))+","+ \
		usage_value_string+","+ \
		str(try_get_value(limits_dict[resource_label], "lower"))+","+ \
		str(try_get_value(resources_dict[resource_label], "min")))

def print_debug_info(container, usages, triggered_events, triggered_requests):
	resources = container["resources"]
	limits = database_handler.get_limits(container)["resources"]
	print " @" + container["name"]
	print "   #RESOURCES: " + \
		"cpu(" + print_container_status("cpu", resources, limits, usages) + ")"+ \
		 " - " + \
		"mem(" + print_container_status("mem", resources, limits, usages) + ")"
		
	events = []
	for event in triggered_events: events.append(event["name"])
	requests = []
	for request in triggered_requests: requests.append(request["action"])
	
	print "   #TRIGGERED EVENTS " + str(events) + " AND TRIGGERED REQUESTS " + str(requests)
	
	
def pet_watchdog(stage, delta):
	print "Reached stage: " + stage + " at time: " + str("%.2f" % (time.time() - delta))
	return time.time()

def guard():
	epoch = 0
	while True:
		# For debug output only
		epoch += 1 
		epoch_start = time.time()
		print "EPOCH: " + str(epoch) + " at time: " + time.strftime("%D %H:%M:%S", time.localtime())
		####
		
		rules = database_handler.get_rules()
		config = database_handler.get_all_database_docs("config")[0] #FIX
		window_difference = get_config_value(config, "WINDOW_TIMELAPSE")
		window_delay = get_config_value(config, "WINDOW_DELAY")
		event_timeout = get_config_value(config, "EVENT_TIMEOUT")
		
		containers = database_handler.get_structures(subtype="container")
		for container in containers:
			try:
				#delta = time.time()
				#delta = pet_watchdog("start", delta)
				
				usages = get_structure_usages(container, window_difference, window_delay)
				#delta = pet_watchdog("with monitor data retrieved", delta)
				
				limits = database_handler.get_limits(container)["resources"]
				#delta = pet_watchdog("with limits retrieved", delta)
				triggered_events = match_container_limits(
					container,
					usages, 
					container["resources"],
					limits, 
					rules)
				process_events(triggered_events)
				#delta = pet_watchdog("with events processed", delta)


				events = reduce_structure_events(filter_and_purge_old_events(container, event_timeout))
				#delta = pet_watchdog("with structure events retrieved", delta)
				triggered_requests = match_structure_events(
					container,
					events, 
					rules)
				process_requests(triggered_requests)
				#delta = pet_watchdog("with requests processed", delta)
				
				## DEBUG AND INFO OUTPUT
				print_debug_info(container, usages, triggered_events, triggered_requests)
			
			except Exception as e:
				print "ERROR with container: " + container["name"]
				print str(e)
				traceback.print_exc()
		epoch_end = time.time()
		processing_time = epoch_end - epoch_start
		print "It took " + str(processing_time) + " seconds to process " + str(len(containers)) + " nodes."
		print
			
		time.sleep(window_difference)

guard()

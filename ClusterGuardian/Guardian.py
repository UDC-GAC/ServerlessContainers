#/usr/bin/python
import requests
import json
import re
import time
import sys

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
		return json.loads(r.text)
		

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
		subquery.append(dict(aggregator='sum', metric=metric,tags=dict(host=structure["name"])))
		

	start = int(time.time() - (window_difference + window_delay))
	end = int(time.time() - window_delay)
	query = dict(start=start, end=end, queries=subquery)
	
	result = monitoring_handler.get_points(query)
	
	for metric in result:
		dps = metric["dps"]
		summatory = 0
		for key in dps:
			summatory += dps[key]
		if len(dps) > 0:
			average_real = summatory / len(dps)
		else:
			average_real = 0
		
		usages[metric["metric"]] = average_real
		
	return usages


def purge_old_events(structure, event_timeout):
	structure_events = database_handler.get_events(structure)
	for event in structure_events:
		if event["timestamp"] < time.time() - event_timeout:
			database_handler.delete_event(event)

def get_structure_events(structure):
	structure_events = database_handler.get_events(structure)
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

def guard():
	while True:
		rules = database_handler.get_rules()
		config = database_handler.get_all_database_docs("config")[0] #FIX
		window_difference = get_config_value(config, "WINDOW_TIMELAPSE")
		window_delay = get_config_value(config, "WINDOW_DELAY")
		event_timeout = get_config_value(config, "EVENT_TIMEOUT")
		
		containers = database_handler.get_structures()
		for container in containers:
			usages = get_structure_usages(container, window_difference, window_delay)
			
			triggered_events = match_container_limits(
				container,
				usages, 
				container["resources"],
				database_handler.get_limits(container)["resources"], 
				rules)
			process_events(triggered_events)
			
			purge_old_events(container, event_timeout)
			triggered_requests = match_structure_events(
				container,
				get_structure_events(container), 
				rules)
			process_requests(triggered_requests)
			
			resources = container["resources"]
			print "RESOURCES: " + \
				"cpu" + "("+str(resources["cpu"]["max"])+","+str(resources["cpu"]["min"])+")" + " - " + \
				"mem" + "("+str(resources["mem"]["max"])+","+str(resources["mem"]["min"])+")"+ " - " + \
				"disk" + "("+str(resources["disk"]["max"])+","+str(resources["disk"]["min"])+")"+ " - " + \
				"net" + "("+str(resources["net"]["max"])+","+str(resources["net"]["min"])+")"
			
			limits = database_handler.get_limits(container)["resources"]
			print "LIMITS: "  + \
				"cpu" + "("+str(limits["cpu"]["upper"])+","+str(limits["cpu"]["lower"])+")" + " - " + \
				"mem" + "("+str(limits["mem"]["upper"])+","+str(limits["mem"]["lower"])+")" + " - " + \
				"disk" + "("+str(limits["disk"]["upper"])+","+str(limits["disk"]["lower"])+")" + " - " + \
				"net" + "("+str(limits["net"]["upper"])+","+str(limits["net"]["lower"])+")"
				
			print "USAGES: " + str(usages)
			events = []
			for event in triggered_events: events.append(event["name"])
			print "TRIGGERED EVENTS " + str(events)
			print "NODE EVENTS " + str(json.dumps(get_structure_events(container)))
			
			requests = []
			for request in triggered_requests: requests.append(request)
			print "TRIGGERED REQUESTS " + str(requests)
			print
			
		time.sleep(window_difference)

guard()

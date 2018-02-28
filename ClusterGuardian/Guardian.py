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
	
	def __init__(self, server = 'http://opentsdb:4242'):
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
WINDOW_TIMELAPSE = 10
WINDOW_DELAY = 10
TRIGGER_WINDOW_TIME = 50

NO_METRIC_DATA_DEFAULT_VALUE = -1
## GET THESE VARIABLES FROM STATE DATABASE

def get_node_usages(structure, window_difference, window_delay):
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


def get_node_events(structure, trigger_window_time):
	node_events = database_handler.get_events(structure)
	events_reduced = {"action": {}}
	for resource in RESOURCES:
		events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up":0}}}
		
	for event in node_events:
		if event["timestamp"] < time.time() - trigger_window_time:
			print "Event too old, purge it"
			print event
			database_handler.delete_event(event)
		
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


def match_node_limits(structure, usages, resources, limits, rules):
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
			print json.dumps(rule["rule"])
			print json.dumps(data[rule["resource"]])
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


def match_node_events(structure, events, rules):
	requests = []
	data = events
	for rule in rules:
		if rule["generates"] == "requests":
			if(jsonLogic(rule["rule"], data[rule["resource"]])):
				requests.append(dict(
					type="request", 
					amount=rule["amount"],
					structure=structure["name"], 
					action=rule["action"], 
					timestamp=int(time.time()))
				)
				database_handler.delete_num_events_by_node(structure, generateEventName(data[rule["resource"]]["events"], rule["resource"]), rule["events_to_remove"])
	return requests

def guard():
	while True:
		rules = database_handler.get_rules()
		config = database_handler.get_all_database_docs("config")[0] #FIX
		window_difference = config["guardian_config"]["WINDOW_TIMELAPSE"]
		window_delay = config["guardian_config"]["WINDOW_DELAY"]

		containers = database_handler.get_structures()
		print containers
		for container in containers:
			usages = get_node_usages(container, window_difference, window_delay)
			
			triggered_events = match_node_limits(
				container,
				usages, 
				container["resources"],
				database_handler.get_limits(container)["resources"], 
				rules)
			process_events(triggered_events)
			
			triggered_requests = match_node_events(
				container, 
				get_node_events(container, TRIGGER_WINDOW_TIME), 
				rules)
			process_requests(triggered_requests)
			
			resources = container["resources"]
			print "RESOURCES: " + \
				"cpu" + "("+str(resources["cpu"]["max"])+","+str(resources["cpu"]["current"])+","+str(resources["cpu"]["min"])+")" + " - " + \
				"mem" + "("+str(resources["mem"]["max"])+","+str(resources["mem"]["current"])+","+str(resources["mem"]["min"])+")"+ " - " + \
				"disk" + "("+str(resources["disk"]["max"])+","+str(resources["disk"]["current"])+","+str(resources["disk"]["min"])+")"+ " - " + \
				"net" + "("+str(resources["net"]["max"])+","+str(resources["net"]["current"])+","+str(resources["net"]["min"])+")"
			
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
			print "NODE EVENTS " + str(json.dumps(get_node_events(container, TRIGGER_WINDOW_TIME)))
			
			requests = []
			for request in triggered_requests: requests.append(request["action"]["requests"][0])
			print "TRIGGERED REQUESTS " + str(requests)
			print
			
		time.sleep(window_difference)

guard()

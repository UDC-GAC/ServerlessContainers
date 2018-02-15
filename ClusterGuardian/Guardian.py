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

def get_node_usages(node, window_difference, window_delay):
	usages = dict()
	subquery = list()
	
	for metric in METRICS:
		usages[metric] = -1
		subquery.append(dict(aggregator='sum', metric=metric,tags=dict(host=node["node"])))
		

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


def get_node_events(node):
	node_events = database_handler.get_events(node)
	events_reduced = {"action": {}}
	for resource in RESOURCES:
		events_reduced["action"][resource] = {"events": {"scale": {"down": 0, "up":0}}}
		
	for event in node_events:
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


def match_node_limits(node, usages, resources, limits, rules):
	events = []
	data = {}
	
	for resource in RESOURCES:
		data[resource] = dict()
		data[resource]["proc"] = {}
		data[resource]["limits"] = {}
		data[resource]["nodes"] = {}
		data[resource]["proc"][resource] = dict()
		data[resource]["limits"][resource] = limits[resource]
		data[resource]["nodes"][resource] = resources[resource]
	
	
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
						node=node["node"], 
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


def match_node_events(node, events, rules):
	requests = []
	data = events
	for rule in rules:
		if rule["generates"] == "requests":
			if(jsonLogic(rule["rule"], data[rule["resource"]])):
				requests.append(dict(type="request", node=node["node"], action=rule["action"], timestamp=int(time.time())))
				database_handler.delete_num_events_by_node(node, generateEventName(data[rule["resource"]]["events"], rule["resource"]), rule["events_to_remove"])
	return requests

def guard():
	window_difference = 10
	window_delay = 10
	
	rules = database_handler.get_rules()
	#print "RULES:"
	#print json.dumps(rules)
	print 
	while True:
		nodes = database_handler.get_nodes()
		for node in nodes:
			usages = get_node_usages(node, window_difference, window_delay)
			
			triggered_events = match_node_limits(
				node,
				usages, 
				node["resources"],
				database_handler.get_limits(node)["resources"], 
				rules)
			process_events(triggered_events)
			
			triggered_requests = match_node_events(
				node, 
				get_node_events(node), 
				rules)
			process_requests(triggered_requests)
			
			resources = node["resources"]
			print "RESOURCES: " + \
				"cpu" + "("+str(resources["cpu"]["max"])+","+str(resources["cpu"]["current"])+","+str(resources["cpu"]["min"])+")" + " - " + \
				"mem" + "("+str(resources["mem"]["max"])+","+str(resources["mem"]["current"])+","+str(resources["mem"]["min"])+")"+ " - " + \
				"disk" + "("+str(resources["disk"]["max"])+","+str(resources["disk"]["current"])+","+str(resources["disk"]["min"])+")"+ " - " + \
				"net" + "("+str(resources["net"]["max"])+","+str(resources["net"]["current"])+","+str(resources["net"]["min"])+")"
			
			limits = database_handler.get_limits(node)["resources"]
			print "LIMITS: "  + \
				"cpu" + "("+str(limits["cpu"]["upper"])+","+str(limits["cpu"]["lower"])+")" + " - " + \
				"mem" + "("+str(limits["mem"]["upper"])+","+str(limits["mem"]["lower"])+")" + " - " + \
				"disk" + "("+str(limits["disk"]["upper"])+","+str(limits["disk"]["lower"])+")" + " - " + \
				"net" + "("+str(limits["net"]["upper"])+","+str(limits["net"]["lower"])+")"
				
			print "USAGES: " + str(usages)
			events = []
			for event in triggered_events: events.append(event["name"])
			print "TRIGGERED EVENTS " + str(events)
			print "NODE EVENTS " + str(json.dumps(get_node_events(node)))
			
			requests = []
			for request in triggered_requests: requests.append(request["action"]["requests"][0])
			print "TRIGGERED REQUESTS " + str(requests)
			print
			
		time.sleep(window_difference)

guard()

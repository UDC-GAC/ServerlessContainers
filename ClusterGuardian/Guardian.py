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

def get_node_usages(node, window_difference, window_delay):
	usages = {'proc.cpu.user':-1, 'proc.mem.resident':-1, 'proc.cpu.kernel':-1, 'proc.mem.virtual':-1}
	
	subquery=[dict(aggregator='sum', metric='proc.cpu.user',tags=dict(host=node["node"])),
			  dict(aggregator='sum', metric='proc.cpu.kernel',tags=dict(host=node["node"])),
			  dict(aggregator='sum', metric='proc.mem.resident',tags=dict(host=node["node"])),
			  dict(aggregator='sum', metric='proc.mem.virtual',tags=dict(host=node["node"]))]	
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
	#print(metric["metric"] + " -> " + str(time.strftime('%Y/%m/%d-%H:%M:%S',time.localtime(start))) + " to " + str(time.strftime('%Y/%m/%d-%H:%M:%S',time.localtime(end))) + " for " + str(end - start) + " seconds " + " -> " + str(("%.2f" % round(summatory,2))) + " / " + str(len(dps)) + " = " + str(("%.2f" % round(average_real,2))))


def get_node_events(node):
	node_events = database_handler.get_events(node)
	events_reduced = {"action": {"cpu": {"events": {"scale": {"down": 0, "up":0}}}, "mem":{"events": {"scale": {"down": 0, "up":0}}}}}
	for event in node_events:
		key = event["action"]["events"]["scale"].keys()[0]
		value = event["action"]["events"]["scale"][key]
		events_reduced["action"][event["resource"]]["events"]["scale"][key] += value
	return events_reduced["action"]

def match_node_limits(node, usages, resources, limits, rules):
	events = []
	data = {}
	
	data["cpu"] = dict(
		proc=dict(cpu=dict()),
		limits=dict(cpu=limits["cpu"]),
		nodes=dict(cpu=resources["cpu"])
	)
	data["mem"] = dict(
		proc=dict(mem=dict()),
		limits=dict(mem=limits["mem"]),
		nodes=dict(mem=resources["mem"])
	)
	
	for usage_metric in usages:
		keys = usage_metric.split(".")
		data[keys[1]][keys[0]][keys[1]][keys[2]] = usages[usage_metric]	
	
	for rule in rules:
		if rule["generates"] == "events":
			if(jsonLogic(rule["rule"], data[rule["resource"]])):
				events.append(dict(
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

def match_node_events(node, events, rules):
	requests = []
	data = events
	print json.dumps(events)
	for rule in rules:
		#print json.dumps(rule["rule"])
		#print json.dumps(data)
		if(jsonLogic(rule["rule"], data[rule["resource"]])):
			#print "Rule matched, triggers " + rule["generates"] + " -> " + str(rule["action"][rule["generates"]])
			#for event in rule["action"][rule["generates"]]:
			#	events.append(dict(type="event", node=node["node"], name=event, timestamp=int(time.time())))
			requests.append(dict(type="request", node=node["node"], action=rule["action"], timestamp=int(time.time())))
	return requests

def guard():
	window_difference = 10
	window_delay = 10
	
	rules = database_handler.get_rules()
	print "RULES:"
	print json.dumps(rules)
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
			
			triggered_requests = match_node_events(node, get_node_events(node), rules)
			
			print "RESOURCES: " + str(node["resources"])
			print "LIMITS: " + str(database_handler.get_limits(node)["resources"])
			print "USAGES: " + str(usages)
			print "TRIGGERED EVENTS " + str(triggered_events)
			print "NODE EVENTS " + str(json.dumps(get_node_events(node)))
			print "TRIGGERED REQUESTS " + str(triggered_requests)
			print
			
		time.sleep(window_difference)

guard()

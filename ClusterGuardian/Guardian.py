#/usr/bin/python
from __future__ import print_function
import requests
import json
import re
import time
import sys
import traceback
import logging

sys.path.append('../StateDatabase')
import couchDB

from json_logic import jsonLogic


def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

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

BDWATCHDOG_METRICS = ['proc.cpu.user', 'proc.mem.resident', 'proc.cpu.kernel', 'proc.mem.virtual']

GUARDIAN_METRICS = 	{
	'proc.cpu.user':['proc.cpu.user','proc.cpu.kernel'], 
	'proc.mem.resident':['proc.mem.resident']}

RESOURCES = ['cpu','mem','disk','net']
########################

translator_dict = {"cpu": "proc.cpu.user", "mem":"proc.mem.resident"}

NO_METRIC_DATA_DEFAULT_VALUE = -1

def get_structure_usages(structure, window_difference, window_delay):
	usages = dict()
	subquery = list()
	for metric in BDWATCHDOG_METRICS:
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
	
	final_values = dict()
	
	for value in GUARDIAN_METRICS:
		final_values[value] = 0
		for metric in GUARDIAN_METRICS[value]:
			final_values[value] += usages[metric]
	
	return final_values


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
	data = dict()
		
	for resource in RESOURCES:
		data[resource] = {
				"proc":{resource:{}},
				"limits":{resource:limits[resource]},
				"structure":{resource:resources[resource]}}	
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


def get_amount_from_fit_reduction(structure, usages, resource):
	
	boundary_dict = {"cpu": 25, "mem":1024}
	current_resource_limit = structure["resources"][resource]["current"]
	current_resource_usage = usages[translator_dict[resource]]
	
	difference = current_resource_limit - current_resource_usage
		
	amount = -1 * (difference - boundary_dict[resource])
	return amount

def get_amount_from_percentage_reduction(structure, usages, resource, percentage_reduction):
	current_resource_limit = structure["resources"][resource]["current"]
	current_resource_usage = usages[translator_dict[resource]]
	
	difference = current_resource_limit - current_resource_usage
	
	if percentage_reduction > 50:
		percentage_reduction = 50 # TMP hard fix just in case
	
	amount = int(-1 * (percentage_reduction * difference) / 100)
	return amount

def match_structure_events(structure, events, rules, usages):
	requests = []
	for rule in rules:
		if rule["generates"] == "requests":
			if(jsonLogic(rule["rule"], events[rule["resource"]])):
				# Match, generate request
				if "rescale_by" in rule.keys():
					try:
						if rule["rescale_by"] == "amount":
							amount=rule["amount"]
						elif rule["rescale_by"] == "percentage_reduction":
							amount = get_amount_from_percentage_reduction(
								structure, usages, rule["resource"], int(rule["percentage_reduction"]))					
						elif rule["rescale_by"] == "fit_to_usage":
							amount = get_amount_from_fit_reduction(
								structure, usages, rule["resource"])
						else:
							amount=rule["amount"]
					except KeyError:
						# Error because current value may not be available and it is
						# required for methods like percentage reduction
						amount=rule["amount"]
				else:
					amount=rule["amount"]
					
				requests.append(dict(
					type="request",
					resource=rule["resource"],
					amount=amount,
					structure=structure["name"], 
					action=rule["action"]["requests"][0], 
					timestamp=int(time.time()))
				)
				database_handler.delete_num_events_by_structure(
					structure, 
					generateEventName(events[rule["resource"]]["events"], rule["resource"]), rule["events_to_remove"]
				)
	return requests

def try_get_value(dict, key):
	try:
		#return str("%.2f" % dict[key]) # Float with 2 decimals
		return int(dict[key])
	except KeyError:
		return "n/a"

def print_container_status(resource_label, resources_dict, limits_dict, usages_dict):
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
	print(" @" + container["name"])
	print("   #RESOURCES: " + \
		"cpu(" + print_container_status("cpu", resources, limits, usages) + ")"+ \
		 " - " + \
		"mem(" + print_container_status("mem", resources, limits, usages) + ")")
		
	events = []
	for event in triggered_events: events.append(event["name"])
	requests = []
	for request in triggered_requests: requests.append(request["action"])
	
	print("   #TRIGGERED EVENTS " + str(events) + " AND TRIGGERED REQUESTS " + str(requests))
	


def check_invalid_values(value1, label1, value2, label2):
	if value1 > value2: 
		raise ValueError(
			"value for '" + label1 + "': " + str(value1) + \
			" is greater than " + \
			"value for '" + label2 + "': " + str(value2))

def check_close_boundaries(value1, label1, value2, label2, boundary):
	if value1 - boundary <= value2: 
		raise ValueError(
			"value for '" + label1 + "': " + str(value1) + \
			" is too close ("+str(boundary)+") to " + \
			"value for '" + label2 + "': " + str(value2))
			
def check_invalid_state(container):
	resources = container["resources"]
	limits = database_handler.get_limits(container)["resources"]
	
	resources_boundaries = {"cpu":15,"mem":170} # Better don't set multiples of steps
	
	for resource in ["cpu","mem"]:
		max_value = try_get_value(resources[resource], "max")
		current_value = try_get_value(resources[resource], "current")
		upper_value = try_get_value(limits[resource], "upper")
		lower_value = try_get_value(limits[resource], "lower")
		min_value = try_get_value(resources[resource], "min")
		
		# Check if the first value is greater than the second
		# check the full chain max > upper > current > lower > min
		if current_value != "n/a":
			check_invalid_values(min_value, "current", max_value, "max")
		check_invalid_values(upper_value, "upper", current_value, "current")
		check_invalid_values(lower_value, "lower", upper_value, "upper")
		#check_invalid_values(min_value, "min", lower_value, "lower")
		
		try:
			# Check that there is a boundary between values, like the current and upper, so
			# that the limit can be surpassed
			if current_value != "n/a":
				check_close_boundaries(current_value, "current", upper_value, "upper", resources_boundaries[resource])
		except ValueError as e:
			logging.warning(str(e))
		

CONFIG_DEFAULT_VALUES = {"WINDOW_TIMELAPSE":10, "WINDOW_DELAY":10, "EVENT_TIMEOUT":40, "DEBUG":True}
def get_config_value(config, key):
	try:
		return config[key]
	except KeyError:
		logging.warning("Failed to get config key: " + key)
		return CONFIG_DEFAULT_VALUES[key]
		
def pet_watchdog(stage, delta):
	print("Reached stage: " + stage + " at time: " + str("%.2f" % (time.time() - delta)))
	return time.time()
	
def guard():
	logging.basicConfig(filename='Guardian.log', level=logging.INFO)
	
	while True:	
		service = database_handler.get_service("guardian")
		
		# HEARTBEAT
		service["heartbeat"] =  time.strftime("%D %H:%M:%S", time.localtime())
		database_handler.update_doc("services", service)
		
		epoch_start = time.time()
		
		# CONFIG
		rules = database_handler.get_rules()
		config = service["config"]
		window_difference = get_config_value(config, "WINDOW_TIMELAPSE")
		window_delay = get_config_value(config, "WINDOW_DELAY")
		event_timeout = get_config_value(config, "EVENT_TIMEOUT")
		debug = get_config_value(config, "DEBUG")
		benchmark = False
		
		containers = database_handler.get_structures(subtype="container")
		for container in containers:
			try:
				check_invalid_state(container)
				
				if benchmark: delta = time.time()
				if benchmark: delta = pet_watchdog("start", delta)
				
				usages = get_structure_usages(container, window_difference, window_delay)
				if benchmark: delta = pet_watchdog("with monitor data retrieved", delta)
				limits = database_handler.get_limits(container)["resources"]
				if benchmark: delta = pet_watchdog("with limits retrieved", delta)
				triggered_events = match_container_limits(
					container,
					usages, 
					container["resources"],
					limits, 
					rules)
				process_events(triggered_events)

				
				events = reduce_structure_events(filter_and_purge_old_events(container, event_timeout))
				if benchmark: delta = pet_watchdog("with structure events retrieved", delta)
				triggered_requests = match_structure_events(
					container,
					events, 
					rules,
					usages)
				process_requests(triggered_requests)
				if benchmark: delta = pet_watchdog("with requests processed", delta)
				
				## DEBUG AND INFO OUTPUT
				if debug: print_debug_info(container, usages, triggered_events, triggered_requests)
			
			except Exception as e:
				eprint("ERROR with container: " + container["name"])
				eprint(str(e))
				traceback.print_exc()
		epoch_end = time.time()
		processing_time = epoch_end - epoch_start
		
		time_message = "It took " +  str("%.2f" % processing_time) + " seconds to process " + str(len(containers)) + " nodes."
		if debug: print(time_message)
		logging.info(time_message)
		
		time.sleep(window_difference)


def main():
	guard()

if __name__ == "__main__":
	main()	


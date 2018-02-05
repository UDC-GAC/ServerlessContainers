#/usr/bin/python
import requests
import json
import re

class CouchDBServer:
	
	post_doc_headers = {'content-type': 'application/json'}
	databases = ['nodes','limits','events','rules','requests']
	
	def __init__(self, server = 'http://couchdb:5984'):
		if self.check_valid_url(server):
			self.server = server
		else:
			raise ValueError("Invalid server url %s", server)

	def check_valid_url(self, url):
		return True

	def database_exists(self, database):
		r = requests.head(self.server + "/"  + database)
		return r.status_code == 200
		
	def create_database(self, database):
		r = requests.put(self.server + "/"  + database)
		if r.status_code != 201:
			r.raise_for_status()
		else:
			return True
	
	def create_all_dbs(self):
		print ("Creating all databases")
		for database in self.databases:
			if self.create_database(database):
				print("Database " + database + " created")
				
	def remove_database(self, database):
		r = requests.delete(self.server + "/"  + database)
		if r.status_code != 200:
			r.raise_for_status()
		else:
			return True
			
	def remove_all_dbs(self):
		print ("Removing all databases")
		for database in self.databases:
			try:
				if self.remove_database(database):
					print("Database " + database + " removed")
			except(requests.exceptions.HTTPError):
				pass

	def get_all_database_docs(self, database):
		docs = list()
		r = requests.get(self.server + "/"  + database + "/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/" + database + "/" + row["id"])
				docs.append(dict(req_doc.json()))
			return docs

	def delete_doc(self, database, id, rev):
		r = requests.delete(self.server + "/" + database + "/" + str(id) + "?rev=" + str(rev))
		if r.status_code != 200:
			r.raise_for_status()
		else:
			return True

	def add_doc(self, database, doc):
		r = requests.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
		if r.status_code != 200:
			r.raise_for_status()
		else:
			return True

	def update_doc(self, database, doc):
		r = requests.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
		if r.status_code != 200:
			r.raise_for_status()
		else:
			return True


	def get_nodes(self, type="container"):
		docs = list()
		r = requests.get(self.server + "/nodes/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/nodes/" + row["id"])
				if req_doc.json()["type"] == type:
					docs.append(dict(req_doc.json()))
			return docs
	
	def get_events(self, node, event=None):
		docs = list()
		r = requests.get(self.server + "/events/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/events/" + row["id"])
				if req_doc.json()["node"] == node:
					if event!=None and event == req_doc.json()["name"]:
						docs.append(dict(req_doc.json()))
					else:
						docs.append(dict(req_doc.json()))
			return docs

	def delete_events(self, node):
		docs = list()
		r = requests.get(self.server + "/events/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/events/" + row["id"])
				if req_doc.json()["node"] == node:
					self.delete_event(row)

	def delete_event(self, event):
		self.delete_doc("events", event["id"], event["value"]["rev"])

	def get_limits(self, node):
		docs = list()
		r = requests.get(self.server + "/limits/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/limits/" + row["id"])
				if req_doc.json()["node"] == node:
					docs.append(dict(req_doc.json()))
			return docs

	def get_requests(self, node=None):
		docs = list()
		r = requests.get(self.server + "/requests/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/requests/" + row["id"])
				if node!=None:
					if req_doc.json()["node"] == node:
						docs.append(dict(req_doc.json()))
				else:
					docs.append(dict(req_doc.json()))
			return docs

	def delete_request(self, request):
		self.delete_doc("requests", request["id"], request["value"]["rev"])
		
	def delete_requests(self, node):
		docs = list()
		r = requests.get(self.server + "/requests/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/requests/" + row["id"])
				if req_doc.json()["node"] == node:
					self.delete_request(row)

handler = CouchDBServer()
handler.remove_all_dbs()
handler.create_all_dbs()

# CREATE LIMITS
if handler.database_exists("limits"):
	print ("Adding 'limits' documents")
	node0 = dict(_id = 'node0', node='node0', cpu=dict(upper=2,lower=1), memory=dict(upper=1024,lower=512), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	node1 = dict(_id = 'node1', node='node1', cpu=dict(upper=3,lower=1), memory=dict(upper=2048,lower=1024), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	node2 = dict(_id = 'node2', node='node2', cpu=dict(upper=4,lower=1), memory=dict(upper=4096,lower=2048), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	node3 = dict(_id = 'node3', node='node3', cpu=dict(upper=4,lower=1), memory=dict(upper=4096,lower=2048), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	handler.add_doc("limits", node0)
	handler.add_doc("limits", node1)
	handler.add_doc("limits", node2)
	handler.add_doc("limits", node3)

# CREATE NODES
if handler.database_exists("nodes"):
	print ("Adding 'nodes' documents")
	node0 = dict(_id = 'node0', type='container', name='node0', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	node1 = dict(_id = 'node1', type='container', name='node1', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	node2 = dict(_id = 'node2', type='vm', name='node2', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	node3 = dict(_id = 'node3', type='vm', name='node3', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	handler.add_doc("nodes", node0)
	handler.add_doc("nodes", node1)
	handler.add_doc("nodes", node2)
	handler.add_doc("nodes", node3)
	
# CREATE RULES
if handler.database_exists("rules"):
	print ("Adding 'rules' documents")
	exceeded_upper = dict(_id = 'exceeded_upper', type='rule', name='exceeded_upper', rule=dict({"and":[{">":[{"var": "usages.cpu"},{"var": "limits.cpu.upper"}]},{"<":[{"var": "limits.cpu.upper"},{"var": "nodes.cpu.max"}]}]}), action={"events":["bottCPU"]})
	dropped_lower = dict(_id = 'dropped_lower', type='rule', name='dropped_lower', rule=dict({"and":[{"<":[{"var": "usages.cpu"},{"var": "limits.cpu.lower"}]},{">":[{"var": "limits.cpu.lower"},{"var": "nodes.cpu.min"}]}]}), action={"events":["underCPU"]})
	handler.add_doc("rules", exceeded_upper)
	handler.add_doc("rules", dropped_lower)

# CREATE EVENTS
if handler.database_exists("rules"):
	print ("Adding 'events' documents")
	bottCPU = dict(type='event', node='node0', name='bottCPU')
	underCPU = dict(type='event', node='node1', name='underCPU')
	handler.add_doc("events", bottCPU)
	handler.add_doc("events", bottCPU)
	handler.add_doc("events", underCPU)
	handler.add_doc("events", underCPU)
	handler.add_doc("events", underCPU)

# CREATE REQUESTS
if handler.database_exists("requests"):
	print ("Adding 'events' documents")
	ScaleUpCpu = dict(type='request', node='node0', name='ScaleUpCpu')
	ScaleDownCpu = dict(type='request', node='node1', name='ScaleDownCpu')
	handler.add_doc("requests", ScaleUpCpu)
	handler.add_doc("requests", ScaleDownCpu)


print
# LIST ALL
print("#LIMITS")
print(handler.get_all_database_docs("limits"))
print

print("#NODES")
print(handler.get_all_database_docs("nodes"))
print

print("#RULES")
print(handler.get_all_database_docs("rules"))
print

print("#EVENTS")
print(handler.get_all_database_docs("events"))
print

print("container nodes")
print(handler.get_nodes("container"))
print

print("vm nodes")
print(handler.get_nodes("vm"))
print

print("node0 events")
print(handler.get_events("node0"))
print

print("node1 underCPU events")
print(handler.get_events("node1","underCPU"))
print

print("node0 limits")
print(handler.get_limits("node0"))
print

print("requests")
print(handler.get_requests())
print

print("node0 requests")
print(handler.get_requests("node0"))
print

handler.delete_events("node0")
handler.delete_requests("node0")

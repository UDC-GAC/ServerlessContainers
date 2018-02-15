#/usr/bin/python
import requests
import json

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

	def get_nodes(self, type="node"):
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
				if req_doc.json()["node"] == node["node"]:
					docs.append(dict(req_doc.json()))
			return docs

	def delete_num_events_by_node(self, node, event_name, event_num):
		docs = list()
		num_deleted = 0
		r = requests.get(self.server + "/events/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				event = requests.get(self.server + "/events/" + row["id"]).json()
				if event["node"] == node["node"] and event["name"] == event_name and num_deleted < event_num:
					self.delete_event(row)
					num_deleted += 1

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
				if req_doc.json()["node"] == node["node"]:
					return(dict(req_doc.json()))
			
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

	def get_rules(self):
		docs = list()
		r = requests.get(self.server + "/rules/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/rules/" + row["id"])
				docs.append(dict(req_doc.json()))
			return docs

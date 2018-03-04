#/usr/bin/python
import requests
import json

class CouchDBServer:
	
	post_doc_headers = {'content-type': 'application/json'}
	
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
	
	def remove_database(self, database):
		r = requests.delete(self.server + "/"  + database)
		if r.status_code != 200:
			r.raise_for_status()
		else:
			return True
	
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
	
	def get_structures(self, subtype=None):
		docs = list()
		if subtype == None:
			subtype = "container"
		
		query = {"selector": {"subtype": subtype}}
		req_docs = requests.post(self.server + "/structures/_find", data=json.dumps(query), headers = {'Content-Type': 'application/json'})
		if req_docs.status_code != 200:
			req_docs.raise_for_status()
		else:
			return req_docs.json()["docs"]
	
	
	def get_structure(self, structure_name):
		docs = list()
		r = requests.get(self.server + "/structures/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/structures/" + row["id"])
				if req_doc.json()["name"] == structure_name:
					return(dict(req_doc.json()))
			
	def get_events(self, structure):
		query = {"selector": {"structure": structure["name"]}}
		req_docs = requests.post(self.server + "/events/_find", data=json.dumps(query), headers = {'Content-Type': 'application/json'})
		
		if req_docs.status_code != 200:
			req_docs.raise_for_status()
		else:
			return req_docs.json()["docs"]

	def delete_num_events_by_structure(self, structure, event_name, event_num):
		docs = list()
		num_deleted = 0
		r = requests.get(self.server + "/events/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				event = requests.get(self.server + "/events/" + row["id"]).json()
				if event["structure"] == structure["name"] and event["name"] == event_name and num_deleted < event_num:
					self.delete_event(dict(_id = row["id"], _rev=row["value"]["rev"]))
					num_deleted += 1

	def delete_event(self, event):
		self.delete_doc("events", event["_id"], event["_rev"])

	
	def get_limits(self, structure):
		query = {"selector": {"structure": structure["name"]}}
		req_docs = requests.post(self.server + "/limits/_find", data=json.dumps(query), headers = {'Content-Type': 'application/json'})
		
		if req_docs.status_code != 200:
			req_docs.raise_for_status()
		else:
			# Return just the first item, as it should only be one
			return req_docs.json()["docs"][0]
	
	
	def get_requests(self, structure=None):
		
		if structure!=None:
			query = {"selector": {"structure": structure["name"]}}
			req_docs = requests.post(self.server + "/requests/_find", data=json.dumps(query), headers = {'Content-Type': 'application/json'})
			
			if req_docs.status_code != 200:
				req_docs.raise_for_status()
			else:
				return req_docs.json()["docs"]
		else:
			docs = list()
			req_docs = requests.get(self.server + "/requests/_all_docs")
			if req_docs.status_code != 200:
				req_docs.raise_for_status()
			else:
				rows = json.loads(req_docs.text)["rows"]
				for row in rows:
					req_doc = requests.get(self.server + "/requests/" + row["id"])
					docs.append(dict(req_doc.json()))
				return docs
	
	#def get_requests(self, structure=None):
		#docs = list()
		#r = requests.get(self.server + "/requests/_all_docs")
		#if r.status_code != 200:
			#r.raise_for_status()
		#else:
			#rows = json.loads(r.text)["rows"]
			#for row in rows:
				#req_doc = requests.get(self.server + "/requests/" + row["id"])
				#if structure!=None:
					#if req_doc.json()["structure"] == structure["name"]:
						#docs.append(dict(req_doc.json()))
				#else:
					#docs.append(dict(req_doc.json()))
			#return docs

	def delete_request(self, request):
		self.delete_doc("requests", request["_id"], request["_rev"])
		
	def delete_requests(self, structure):
		docs = list()
		r = requests.get(self.server + "/requests/_all_docs")
		if r.status_code != 200:
			r.raise_for_status()
		else:
			rows = json.loads(r.text)["rows"]
			for row in rows:
				req_doc = requests.get(self.server + "/requests/" + row["id"])
				if req_doc.json()["structure"] == structure["name"]:
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

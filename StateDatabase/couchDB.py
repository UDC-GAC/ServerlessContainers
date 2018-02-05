#/usr/bin/python

import requests
import json

server = 'http://couchdb:5984/'
post_doc_headers = {'content-type': 'application/json'}


def create_database(server, database):
	r = requests.put(server + database)
	return r.status_code == 201

def remove_database(server, database):
	r = requests.delete(server + database)
	return r.status_code == 200

def database_exists(server, database):
	r = requests.head(server + database)
	return r.status_code == 200

def get_all_database_docs(server, database):
	docs = list()
	r = requests.get(server + database + "/_all_docs")
	rows = json.loads(r.text)["rows"]
	for row in rows:
		req_doc = requests.get(server + "/"+ database + "/" + row["id"])
		docs.append(dict(req_doc.json()))
	return docs

def add_doc(server, database, doc):
	r = requests.post(server + database, data=json.dumps(doc), headers=post_doc_headers)
	return r.status_code == 201



# REMOVE DATABASES
def remove_all_dbs():
	print ("Removing all databases")
	if remove_database(server,"specs"):
		print("Database 'specs' removed")
	if remove_database(server,"limits"):
		print("Database 'limits' removed")
	if remove_database(server,"rules"):
		print("Database 'rules' removed")
	if remove_database(server,"requests"):
		print("Database 'requests' removed")
	if remove_database(server,"events"):
		print("Database 'events' removed")


# CREATE DATABASES
def create_all_dbs():
	if create_database(server,"specs"):
		print("Database 'specs' created")
	if create_database(server,"limits"):
		print("Database 'limits' created")
	if create_database(server,"rules"):
		print("Database 'rules' created")
	if create_database(server,"requests"):
		print("Database 'requests' created")
	if create_database(server,"events"):
		print("Database 'events' created")


remove_all_dbs()
create_all_dbs()

# CREATE LIMITS
if database_exists(server, "limits"):
	print ("Adding 'limits' documents")
	
	node0 = dict(_id = 'node0', type='container', name='node0', cpu=dict(upper=2,lower=1), memory=dict(upper=1024,lower=512), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	add_doc(server, "limits", node0)
	
	node1 = dict(_id = 'node1', type='container', name='node1', cpu=dict(upper=3,lower=1), memory=dict(upper=2048,lower=1024), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	add_doc(server, "limits", node1)
	
	node2 = dict(_id = 'node2', type='container', name='node2', cpu=dict(upper=4,lower=1), memory=dict(upper=4096,lower=2048), disk=dict(upper=100,lower=100), network=dict(upper=100,lower=100))
	add_doc(server, "limits", node2)

# CREATE SPECS
if database_exists(server, "specs"):
	print ("Adding 'specs' documents")
	
	node0 = dict(_id = 'node0', type='container', name='node0', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	add_doc(server, "specs", node0)
	
	node1 = dict(_id = 'node1', type='container', name='node1', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	add_doc(server, "specs", node1)
	
	node2 = dict(_id = 'node2', type='container', name='node2', cpu=dict(max=4,current=2,min=1), memory=dict(max=4096,current=1024,min=512), disk=dict(max=100,current=100,min=100), network=dict(max=100,current=100,min=100))
	add_doc(server, "specs", node2)
	
# CREATE RULES
if database_exists(server, "rules"):
	print ("Adding 'rules' documents")
	exceeded_upper = dict(_id = 'exceeded_upper', type='rule', name='exceeded_upper', rule=dict({"and":[{">":[{"var": "usages.cpu"},{"var": "limits.cpu.upper"}]},{"<":[{"var": "limits.cpu.upper"},{"var": "specs.cpu.max"}]}]}), action={"events":["scale-up-cpu"]})
	add_doc(server, "rules", exceeded_upper)
	
	dropped_lower = dict(_id = 'dropped_lower', type='rule', name='dropped_lower', rule=dict({"and":[{"<":[{"var": "usages.cpu"},{"var": "limits.cpu.lower"}]},{">":[{"var": "limits.cpu.lower"},{"var": "specs.cpu.min"}]}]}), action={"events":["scale-down-cpu"]})
	add_doc(server, "rules", dropped_lower)
	
# List
print("#LIMITS")
print(get_all_database_docs(server, "limits"))
print("#SPECS")
print(get_all_database_docs(server, "specs"))
print("#RULES")
print(get_all_database_docs(server, "rules"))


#data = {"usages":{"cpu":110}, "limits":{"cpu":{"upper":30}}, "specs":{"cpu":{"max":200}}}

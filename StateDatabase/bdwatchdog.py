#/usr/bin/python
import requests
import json

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

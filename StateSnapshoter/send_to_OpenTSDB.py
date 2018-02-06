#!/usr/bin/env python
from __future__ import print_function
import sys
import fileinput
from subprocess import call
import json
import requests
import gzip
import StringIO
import time
import os

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)
	
## ENVIRONMENT VARIABLES ##
POST_ENDPOINT_VARIABLE = "POST_ENDPOINT_PATH"
POST_DOC_BUFFER_LENGTH = "POST_DOC_BUFFER_LENGTH"
POST_DOC_BUFFER_TIMEOUT = "POST_DOC_BUFFER_TIMEOUT"
POST_SEND_DOCS_TIMEOUT = "POST_SEND_DOCS_TIMEOUT"
POST_SEND_DOCS_FAILED_TRIES = "POST_SEND_DOCS_FAILED_TRIES"


post_endpoint = os.getenv(POST_ENDPOINT_VARIABLE, 'http://opentsdb:4242/api/put')
post_doc_buffer_length = int(os.getenv(POST_DOC_BUFFER_LENGTH, 700))
post_doc_buffer_timeout = int(os.getenv(POST_DOC_BUFFER_TIMEOUT, 5))
post_send_docs_timeout = int(os.getenv(POST_SEND_DOCS_TIMEOUT, 6))
post_send_docs_failed_tries = int(os.getenv(POST_SEND_DOCS_FAILED_TRIES, 3))


## PROGRAM VARIABLES ##
current_timestamp = time.time()
last_timestamp = time.time()
failed_connections = 0
abort = False
headers = {"Content-Type":"application/json", "Content-Encoding":"gzip"}
json_documents = []

try:
	for line in fileinput.input():
		try:
			new_doc = json.loads(line)
			json_documents = json_documents + [new_doc]
		except ValueError:
			eprint ("Error with document " + str(line))
			continue

		current_timestamp = int(new_doc["timestamp"])
		time_diff = current_timestamp - last_timestamp
		length_docs = len(json_documents)
		if(length_docs >= post_doc_buffer_length or time_diff > post_doc_buffer_timeout):
			last_timestamp = current_timestamp
			out = StringIO.StringIO()
			with gzip.GzipFile(fileobj=out, mode="w") as f:
				f.write(json.dumps(json_documents))
			payload = out.getvalue()            
			
			try:
				r = requests.post(post_endpoint, headers = headers, data = out.getvalue(), timeout = post_send_docs_timeout) # 1 second timeout
				#print(r.status_code)
				if r.status_code != 204 and r.status_code != 400: 
					# 200 all data posted successfully, 400 some data had errors 
					eprint("[TSDB SENDER] couldn't properly post documents to address " + post_endpoint)
				else:
					if r.status_code == 400:
						print(r.text)
					print ("Post was done at: " +  time.strftime("%D %H:%M:%S", time.localtime()) + " with " + str(length_docs) + " documents")
				failed_connections = 0 #Reset failed connections, at least this one was successfull now
			except(requests.exceptions.ConnectTimeout):
				failed_connections += 1
				eprint("[TSDB SENDER] couldn't send documents to address " + post_endpoint + " and tried for " + str(failed_connections) + " times")
				if failed_connections >= post_send_docs_failed_tries :
					abort = True
			json_documents = []
			if abort : exit(1)
			sys.stdout.flush()
except IOError as e:
	eprint("[TSDB SENDER] terminated")
	eprint(e)
	pass
except (KeyboardInterrupt):
	eprint("[TSDB SENDER] terminated")
	pass		
		
		
		

# /usr/bin/python
import StateDatabase.couchDB as couchDB
import sys

handler = couchDB.CouchDBServer()


containers = ["node0","node1","node2","node3"]

def resilient_update(doc, container):
    success = False
    max_tries = 10
    tries = 0
    while not success and tries < max_tries:
        try:
            handler.update_limit(doc)
            success = True
        except Exception:
            new_doc = handler.get_limits(container)
            doc["_rev"] = new_doc["_rev"]
            tries += 1

for c in containers:
    container = handler.get_structure(c)
    limits = handler.get_limits(container)
    limits["resources"]=dict(
        cpu=dict(upper=170, lower=150),
        mem=dict(upper=8000, lower=7000),
        disk=dict(upper=100, lower=100),
        net=dict(upper=100, lower=100),
        energy=dict(upper=15, lower=5)
    )
    resilient_update(limits, container)

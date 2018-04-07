# /usr/bin/python
import StateDatabase.couchDB as couchDB

handler = couchDB.CouchDBServer()

containers = ["node0","node1","node2","node3"]

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
    handler.update_limit(limits)

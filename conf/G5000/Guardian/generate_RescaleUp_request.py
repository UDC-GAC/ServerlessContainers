import time

from src.StateDatabase import couchdb

for node in ["node0","node1","node2","node3"]:
    request = dict(
        type="request",
        resource="cpu",
        amount=int(100),
        structure=node,
        action="RescaleCpuUp",
        timestamp=int(time.time())
    )
    request["host"] = "host0"
    request["host_rescaler_ip"] = "host0"
    request["host_rescaler_port"] = "8000"

    couchdb_handler = couchdb.CouchDBServer()
    couchdb_handler.add_request(request)
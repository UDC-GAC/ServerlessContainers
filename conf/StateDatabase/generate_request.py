# /usr/bin/python
from sys import argv

import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils
from src.Guardian.Guardian import Guardian

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()

    struct_name = argv[1]
    struct_type = argv[2]
    resource_label = argv[3]
    amount = argv[4]

    structure = {"name": struct_name, "subtype": struct_type}

    if struct_type == "container":
        structure["host"] = "host0"
        structure["host_rescaler_ip"] = "host0"
        structure["host_rescaler_port"] = "8000"

    request = Guardian.generate_request(structure, amount, resource_label)
    print(request)
    handler.add_request(request)
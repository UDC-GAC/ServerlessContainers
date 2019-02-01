# /usr/bin/python
import json
import time

import StateDatabase.couchdb as couchDB


def dump_to_file(filename, content):
    with open(filename, 'w') as f:
        f.write(content)


def clean_document(document):
    keys_to_remove = "_id", "_rev", "heartbeat", "heartbeat_human"
    for key in keys_to_remove:
        if key in document:
            del (document[key])
    return document


def clean_structure(structure):
    structure = clean_document(structure)

    keys_to_remove = "host_rescaler_ip", "host_rescaler_port", "guard_policy", "guard"
    for key in keys_to_remove:
        if key in structure:
            del (structure[key])

    resource_keys_to_remove = "current", "fixed", "boundary", "usage", "guard"
    for resource in structure["resources"]:
        for key in resource_keys_to_remove:
            if key in structure["resources"][resource]:
                del (structure["resources"][resource][key])
    return structure

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()
    all_info = dict()

    for service_name in ["guardian", "scaler", "database_snapshoter", "structures_snapshoter", "refeeder",
                         "sanity_checker"]:
        service = handler.get_service(service_name)
        all_info[service_name] = clean_document(service)

    for rule_name in ["cpu_exceeded_upper", "cpu_dropped_lower", "CpuRescaleUp", "CpuRescaleDown", "mem_exceeded_upper",
                      "mem_dropped_lower", "MemRescaleUp", "MemRescaleDown"]:
        rule = handler.get_rule(rule_name)
        all_info[rule_name] = clean_document(rule)

    for structure_name in ["node0", "node1", "node2", "node3", "node4", "node5", "node6", "node7", "node8", "node9",
                           "node10", "node11"]:
        structure = handler.get_structure(structure_name)
        all_info[structure_name] = clean_structure(structure)

    filename = time.strftime("%d-%m-%y-%H:%M", time.localtime()) + ".json"
    dump_to_file(filename, json.dumps(all_info, sort_keys=True, indent=4))

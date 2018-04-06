# /usr/bin/python
import StateDatabase.couchDB as couchDB
import sys

handler = couchDB.CouchDBServer()


def resilient_update(doc, update_funct, retrieve_funct):
    success = False
    max_tries = 10
    tries = 0
    while not success and tries < max_tries:
        try:
            update_funct(doc)
            success = True
        except Exception:
            new_doc = retrieve_funct(doc["name"])
            doc["_rev"] = new_doc["_rev"]
            doc["heartbeat"] = new_doc["heartbeat"]
            tries += 1


def switch_to_container(guardian):
    guardian["config"]["STRUCTURE_GUARDED"] = "container"
    resilient_update(guardian, handler.update_service, handler.get_service)
    rules = handler.get_rules()
    for rule in rules:
        if "rescale_by" in rule:

            if rule["name"].endswith("Down"):
                rule["rescale_by"] = "fit_to_usage"

            if rule["name"].endswith("Up"):
                rule["rescale_by"] = "amount"

            resilient_update(rule,handler.update_rule, handler.get_rule)


def switch_to_application(guardian):
    guardian["config"]["STRUCTURE_GUARDED"] = "application"
    resilient_update(guardian, handler.update_service, handler.get_service)
    rules = handler.get_rules()
    for rule in rules:
        if "rescale_by" in rule:

            rule["rescale_by"] = "amount"
            resilient_update(rule,handler.update_rule, handler.get_rule)


def main(argv):
    if len(argv) == 0:
        print("No operation specified")

    op = argv[0]
    guardian = handler.get_service("guardian")
    if op == "switch_to_app":
        switch_to_application(guardian)
    elif op == "switch_to_container":
        switch_to_container(guardian)
    else:
        print("Unrecognized op")


if __name__ == "__main__":
    main(sys.argv[1:])

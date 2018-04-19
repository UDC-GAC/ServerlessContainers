# /usr/bin/python
import StateDatabase.couchDB as couchDB
import sys

handler = couchDB.CouchDBServer()


def switch_to_container(guardian):
    guardian["config"]["STRUCTURE_GUARDED"] = "container"
    handler.update_service(guardian)
    rules = handler.get_rules()
    for rule in rules:
        if "rescale_by" in rule:

            if rule["name"].endswith("Down"):
                rule["rescale_by"] = "fit_to_usage"

            if rule["name"].endswith("Up"):
                rule["rescale_by"] = "amount"

            handler.update_rule(rule)


def switch_to_application(guardian):
    guardian["config"]["STRUCTURE_GUARDED"] = "application"
    handler.update_service(guardian)
    rules = handler.get_rules()
    for rule in rules:
        if "rescale_by" in rule:

            if rule["name"].endswith("Down"):
                rule["rescale_by"] = "fit_to_usage"

            if rule["name"].endswith("Up"):
                rule["rescale_by"] = "amount"

            handler.update_rule(rule)


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

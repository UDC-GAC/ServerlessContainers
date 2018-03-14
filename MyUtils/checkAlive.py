# /usr/bin/python
import time
import requests
import StateDatabase.couchDB as couchDB

db = couchDB.CouchDBServer()
time_window_allowed = 20  # 1 minute
POLLING_TIME = 5


def check_node_rescaler_status(node_rest_endpoint):
    try:
        r = requests.get("http://" + node_rest_endpoint + ":8000/heartbeat", headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.ConnectionError:
        return False


def print_dead(service_name):
    print(service_name + " -> " + "DEAD")


def print_alive(service_name):
    print(service_name + " -> " + "ALIVE")


while True:
    services = db.get_all_database_docs("services")
    print("AT: " + str(time.strftime("%D %H:%M:%S", time.localtime())))
    for service in services:
        if "heartbeat" not in service:
            print_dead(service["name"])
        elif not isinstance(service["heartbeat"], int) and not isinstance(service["heartbeat"], float):
            print_dead(service["name"])
        elif int(service["heartbeat"]) == 0:
            print_dead(service["name"])
        elif service["heartbeat"] < time.time() - time_window_allowed:
            print_dead(service["name"])
        else:
            print_alive(service["name"])

    for node_REST_service in ["dante"]:
        if check_node_rescaler_status(node_REST_service):
            print_alive(node_REST_service + "_node_rescaler")
        else:
            print_dead(node_REST_service + "_node_rescaler")

    print
    time.sleep(POLLING_TIME)

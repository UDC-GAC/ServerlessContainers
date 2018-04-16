# /usr/bin/python
import time
import requests
import StateDatabase.couchDB as couchDB

db = couchDB.CouchDBServer()
time_window_allowed = 20  # 1 minute
POLLING_TIME = 2


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
    dead = list()
    alive = list()

    services = db.get_all_database_docs("services")

    for service in services:
        if "heartbeat" not in service:
            dead.append(service["name"])
        elif not isinstance(service["heartbeat"], int) and not isinstance(service["heartbeat"], float):
            dead.append(service["name"])
        elif int(service["heartbeat"]) == 0:
            dead.append(service["name"])
        elif service["heartbeat"] < time.time() - time_window_allowed:
            dead.append(service["name"])
        else:
            alive.append(service["name"])

    for node_REST_service in ["dante"]:
        if check_node_rescaler_status(node_REST_service):
            alive.append(node_REST_service + "_node_rescaler")
        else:
            dead.append(node_REST_service + "_node_rescaler")

    print("AT: " + str(time.strftime("%D %H:%M:%S", time.localtime())))
    print
    print("!---- ALIVE ------!")
    for a in alive:
        print(a)
        #print_alive(a)

    print
    print("!---- DEAD -------!")
    for d in dead:
        print(d)
        #print_dead(d)

    print("")
    time.sleep(POLLING_TIME)

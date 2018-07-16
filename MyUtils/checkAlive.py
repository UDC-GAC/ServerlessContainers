# /usr/bin/python
import time
import requests
import StateDatabase.couchDB as couchDB

db = couchDB.CouchDBServer()
time_window_allowed = 20  # 1 minute
POLLING_TIME = 2


def check_rest_api(rest_endpoint):
    try:
        endpoint = "http://{0}:8000/heartbeat".format(rest_endpoint)
        r = requests.get(endpoint, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.ConnectionError:
        print("WARNING -> host: {0} is unresponsive".format(rest_endpoint))
        return False
    except Exception:
        return False


while True:
    dead, alive = list(), list()

    services = db.get_services()

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

    for REST_service in ["dante-rescaler", "orchestrator"]:
        if check_rest_api(REST_service):
            alive.append(REST_service)
        else:
            dead.append(REST_service)

    print("AT: " + str(time.strftime("%D %H:%M:%S", time.localtime())))
    print("")
    print("!---- ALIVE ------!")
    for a in alive:
        print(a)

    print("")
    print("!---- DEAD -------!")
    for d in dead:
        print(d)

    print("")
    time.sleep(POLLING_TIME)

# /usr/bin/python
import time
import requests
import StateDatabase.couchdb as couchDB


def check_rest_api(service_endpoint, service_port):
    try:
        endpoint = "http://{0}:{1}/heartbeat".format(service_endpoint, service_port)
        r = requests.get(endpoint, headers={'Accept': 'application/json'}, timeout=2)
        if r.status_code == 200:
            return True
        else:
            return False
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
        print("WARNING -> host at {0} is unresponsive".format(service_endpoint))
        return False


def classify_service(service_name):
    if service_name.startswith("Atop"):
        return "Atops"
    elif service_name.startswith("Turbostat"):
        return "Turbostats"
    elif service_name.endswith("rescaler"):
        return "Node-Rescalers"
    else:
        return "Others"


def service_is_alive(service, time_window):
    if "heartbeat" not in service:
        return False
    elif not isinstance(service["heartbeat"], int) and not isinstance(service["heartbeat"], float):
        return False
    elif int(service["heartbeat"]) <= 0:
        return False
    elif service["heartbeat"] < time.time() - time_window:
        return False
    else:
        return True


def sort_services_dead_and_alive(services, rest_services, time_window):
    dead, alive = list(), list()
    for service in services:
        if service_is_alive(service, time_window):
            alive.append(service["name"])
        else:
            dead.append(service["name"])

    for rest_service in rest_services:
        service_name, service_endpoint, service_port = rest_service
        if check_rest_api(service_endpoint, service_port):
            alive.append(service_name)
        else:
            dead.append(service_name)

    return dead, alive


def main():
    def print_services(services):
        for service_type in services:
            if services[service_type]:
                print("\t-- {0} --".format(service_type))
                for s in services[service_type]:
                    print("\t" + s)
                print("")

    db = couchDB.CouchDBServer()
    time_window_allowed = 30  # seconds
    POLLING_TIME = 5
    while True:
        #REST_SERVICES = [("orchestrator", "orchestrator", "5000"), ("dante-rescaler", "dante-rescaler", "8000")]
        REST_SERVICES = [("orchestrator", "orchestrator", "5000"), ("c14-1-rescaler", "c14-1-rescaler", "8000"),
                         ("c14-2-rescaler", "c14-2-rescaler", "8000")]
        dead, alive = sort_services_dead_and_alive(db.get_services(), REST_SERVICES, time_window_allowed)

        print("AT: " + str(time.strftime("%D %H:%M:%S", time.localtime())))
        print("")

        print("!---- ALIVE ------!")
        alive_services = {"Atops": list(), "Turbostats": list(), "Node-Rescalers": list(), "Others": list()}
        for a in alive:
            alive_services[classify_service(a)].append(a)
        print_services(alive_services)
        print("")

        print("!---- DEAD -------!")
        dead_services = {"Atops": list(), "Turbostats": list(), "Node-Rescalers": list(), "Others": list()}
        for d in dead:
            dead_services[classify_service(d)].append(d)
        print_services(dead_services)
        print("")

        time.sleep(POLLING_TIME)


if __name__ == "__main__":
    main()

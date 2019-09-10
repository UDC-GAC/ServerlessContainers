# /usr/bin/python
import os

import time
import requests
import src.StateDatabase.couchdb as couchDB


class CheckAliveBase:

    def __init__(self):
        COUCHDB_URL = os.getenv('COUCHDB_URL')
        if not COUCHDB_URL:
            COUCHDB_URL = "couchdb"

        self.__COUCHDB_URL__ = COUCHDB_URL

        self.__POLLING_TIME__ = 5
        self.__MAX_TIME_ALLOWED__ = 30  # seconds

    def set_infrastructure_name(self, INFRASTRUCTURE_NAME):
        self.__INFRASTRUCTURE_NAME__ = INFRASTRUCTURE_NAME

    def set_REST_services(self, REST_SERVICES):
        self.__REST_SERVICES__ = REST_SERVICES

    def __check_rest_api(self, service_endpoint, service_port):
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

    def __classify_service(self, service_name):
        if service_name.startswith("Atop"):
            return "Atops"
        elif service_name.startswith("Turbostat"):
            return "Turbostats"
        elif service_name.endswith("rescaler"):
            return "Node-Rescalers"
        else:
            return "Others"

    def __service_is_alive(self, service, time_window):
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

    def __sort_services_dead_and_alive(self, services, rest_services, time_window):
        dead, alive = list(), list()
        for service in services:
            if self.__service_is_alive(service, time_window):
                alive.append(service["name"])
            else:
                dead.append(service["name"])

        for rest_service in rest_services:
            service_name, service_endpoint, service_port = rest_service
            if self.__check_rest_api(service_endpoint, service_port):
                alive.append(service_name)
            else:
                dead.append(service_name)

        return dead, alive

    def __print_services(self, services):
        for service_type in services:
            if services[service_type]:
                print("\t-- {0} --".format(service_type))
                for s in services[service_type]:
                    print("\t" + s)
                print("")

    def report(self):
        db = couchDB.CouchDBServer(couchdb_url="couchdb".format(self.__INFRASTRUCTURE_NAME__))

        orchestrator_hostname = "orchestrator".format(self.__INFRASTRUCTURE_NAME__)
        self.__REST_SERVICES__.append((orchestrator_hostname, orchestrator_hostname, "5000"))

        while True:
            dead, alive = self.__sort_services_dead_and_alive(db.get_services(), self.__REST_SERVICES__,
                                                            self.__MAX_TIME_ALLOWED__)

            print("AT: " + str(time.strftime("%D %H:%M:%S", time.localtime())))
            print("")

            print("!---- ALIVE ------!")
            alive_services = {"Atops": list(), "Turbostats": list(), "Node-Rescalers": list(), "Others": list()}
            for a in alive:
                alive_services[self.__classify_service(a)].append(a)
            self.__print_services(alive_services)
            print("")

            print("!---- DEAD -------!")
            dead_services = {"Atops": list(), "Turbostats": list(), "Node-Rescalers": list(), "Others": list()}
            for d in dead:
                dead_services[self.__classify_service(d)].append(d)
            self.__print_services(dead_services)
            print("")

            time.sleep(self.__POLLING_TIME__)

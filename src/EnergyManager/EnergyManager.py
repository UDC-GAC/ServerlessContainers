# /usr/bin/python
from __future__ import print_function

import requests
from threading import Thread
import time
import traceback
import logging

import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchdb

CONFIG_DEFAULT_VALUES = {"DEBUG": True, "POLLING_FREQUENCY": 10}
SERVICE_NAME = "energy_manager"


class EnergyManager:

    def __init__(self):
        self.couchdb_handler = couchdb.CouchDBServer()

    def process(self, ):
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
        while True:

            # Get service info
            service = MyUtils.get_service(self.couchdb_handler, SERVICE_NAME)
            config = service["config"]
            self.debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
            polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")

            # Heartbeat
            MyUtils.beat(self.couchdb_handler, SERVICE_NAME)

            # Remote database operation
            users = None
            structures = None
            try:
                structures = MyUtils.get_structures(self.couchdb_handler, self.debug, subtype="application")
                users = self.couchdb_handler.get_users()
            except requests.exceptions.HTTPError as e:
                MyUtils.log_error("Couldn't get users", self.debug)
                MyUtils.log_error(str(e), self.debug)

            for user in users:
                MyUtils.log_info("Processing user {0}".format(user["name"]), self.debug)
                max_energy = user["energy"]["max"]

                # Add up all the shares
                total_shares = 0
                for structure in structures:
                    if structure["name"] in user["clusters"]:
                        total_shares += structure["resources"]["energy"]["shares"]

                total_user_energy = 0
                for structure in structures:
                    if structure["name"] in user["clusters"]:
                        percentage = structure["resources"]["energy"]["shares"] / total_shares
                        limit_energy = max_energy * percentage
                        current_energy = structure["resources"]["energy"]["max"]

                        if current_energy != limit_energy:
                            structure["resources"]["energy"]["max"] = limit_energy
                            self.couchdb_handler.update_structure(structure)

                        MyUtils.log_info("Processed cluster {0} with an energy share of {1}% and {2} Watts".format(
                            structure["name"], str("%.2f" % (100 * percentage)), limit_energy), self.debug)

                        if "used" in structure["resources"]["energy"]:
                            total_user_energy += structure["resources"]["energy"]["used"]

                MyUtils.log_info("Updated energy consumed by user {0}".format(user["name"]), self.debug)
                user["energy"]["used"] = total_user_energy
                self.couchdb_handler.update_user(user)

            MyUtils.log_info(
                "Epoch processed at {0}".format(MyUtils.get_time_now_string()), self.debug)
            time.sleep(polling_frequency)


def main():
    try:
        energy_manager = EnergyManager()
        energy_manager.process()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

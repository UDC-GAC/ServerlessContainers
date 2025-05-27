#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

import requests
import time
import traceback
import logging

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
SERVICE_NAME = "energy_manager"


class EnergyManager:

    def __init__(self):
        self.couchdb_handler = couchdb.CouchDBServer()
        self.polling_frequency, self.debug = None, None

    def process(self, ):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO,
                            format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:
            # Get service info
            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)

            # Print service info
            utils.print_service_config(self, myConfig, self.debug)

            # Remote database operation
            users, structures = None, None
            try:
                structures = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
                users = self.couchdb_handler.get_users()
            except requests.exceptions.HTTPError as e:
                utils.log_error("Couldn't get users", self.debug)
                utils.log_error(str(e), self.debug)
                time.sleep(self.polling_frequency)
                continue

            for user in users:
                utils.log_info("Processing user {0}".format(user["name"]), self.debug)
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

                        utils.log_info("Processed cluster {0} with an energy share of {1}% and {2} Watts".format(
                            structure["name"], str("%.2f" % (100 * percentage)), limit_energy), self.debug)

                        if "used" in structure["resources"]["energy"]:
                            total_user_energy += structure["resources"]["energy"]["used"]

                utils.log_info("Updated energy consumed by user {0}".format(user["name"]), self.debug)
                user["energy"]["used"] = total_user_energy
                self.couchdb_handler.update_user(user)

            utils.log_info(
                "Epoch processed at {0}".format(utils.get_time_now_string()), self.debug)
            time.sleep(self.polling_frequency)


def main():
    try:
        energy_manager = EnergyManager()
        energy_manager.process()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

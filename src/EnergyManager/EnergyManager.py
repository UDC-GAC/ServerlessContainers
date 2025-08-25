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

import traceback

import src.MyUtils.MyUtils as utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True, "ACTIVE": True}


class EnergyManager(Service):

    def __init__(self):
        super().__init__("energy_manager", ConfigValidator(), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.polling_frequency, self.debug, self.active = None, None, None

    def update_energy_limits(self, users, structures):
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

    def work(self, ):
        structures = utils.get_structures(self.couchdb_handler, self.debug, subtype="application")
        users = utils.get_users(self.couchdb_handler, self.debug)
        if structures and users:
            self.update_energy_limits(users, structures)
        else:
            utils.log_warning("No users or structures to process", self.debug)
        return None

    def process(self, ):
        self.run_loop()


def main():
    try:
        energy_manager = EnergyManager()
        energy_manager.process()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

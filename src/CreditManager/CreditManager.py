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

import json
from threading import Thread
import time
import traceback
import logging
import subprocess

from src.Guardian.Guardian import Guardian
from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning, \
    wait_operation_thread, end_epoch, start_epoch
import src.StateDatabase.couchdb as couchdb

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10,
                         "THRESHOLD": 0.1,
                         "ACTIVE": True,
                         "GRIDCOIN_RPC_USER": "gridcoinrpc",
                         "GRIDCOIN_RPC_IP": "192.168.51.100",
                         "GRIDCOIN_RPC_PORT": "9090",
                         "GRIDCOIN_RPC_PASS": "Bt2oEfVgnMGqvB26UapLERmDu5bvULKr9SPvPBkMkMSV",
                         "COINS_TO_CREDIT_RATIO": 600,  # 600 credits per 1 GRC -> 1 vcore for 10 minutes
                         "DEBUG": True}

SERVICE_NAME = "credit_manager"


class CreditManager:

    def __init__(self):
        self.couchdb_handler = couchdb.CouchDBServer()
        self.debug = True
        self.config = {}

    def config_grc_connection(self):
        self.base_call = ["gridcoinresearchd",
                          "-rpcconnect={0}".format(self.grc_ip),
                          "-rpcport={0}".format(self.grc_port),
                          "-rpcuser={0}".format(self.grc_user),
                          "-rpcpassword={0}".format(self.grc_pass)]

    def get_users_wallets(self):
        result = self.run_grc_command(["listaccounts"])
        return json.loads(result)

    def run_grc_command(self, command):
        return subprocess.run(self.base_call + command, stdout=subprocess.PIPE).stdout.decode('utf-8')

    def test_grc_connection(self):
        result = self.run_grc_command(["listaccounts"])
        try:
            json.loads(result)
            return True
        except json.decoder.JSONDecodeError:
            log_error("The response from the RPC command did not return a JSON as expected, check the configuration",
                      self.debug)
            return False

    def move_credit(self, first_user, second_user, amount):
        result = self.run_grc_command(["move", first_user, second_user, amount])
        return result

    def rebase_counters(self, user):
        REBASE_RATIO = 0.1  # Used to module how often a rebase is carried out, 1 -> 1 coin per each fold
        REBASE_BLOCK = int(REBASE_RATIO * self.coins_credit_ratio)
        coins_per_fold = REBASE_RATIO * 1
        accounting = user["accounting"]
        uname = user["name"]

        num_folds = int(accounting["consumed"] / REBASE_BLOCK)
        if num_folds >= 1:
            coins_moved = num_folds * coins_per_fold
            success = self.move_credit(uname, "sink", str(coins_moved))
            if success:
                accounting["consumed"] = round(accounting["consumed"] - num_folds * REBASE_BLOCK, 2)
                log_info("User {0} counters have been rebased".format(uname), self.debug)
            else:
                log_warning("Could not move credit from user {0} to {1}, rebase not carried out".format(uname, "sink"), self.debug)

    def restrict_user(self, user):
        user["accounting"]["restricted"] = True
        # Set containers to unguarded and generate petitions to lower the resources for containers
        apps = user["applications"]
        containers = list()
        requests = list()
        guardian = Guardian()
        for app_name in apps:
            app_info = self.couchdb_handler.get_structure(app_name)
            for cont_name in app_info["containers"]:
                cont_info = self.couchdb_handler.get_structure(cont_name)
                cont_info["guard"] = False
                self.couchdb_handler.update_structure(cont_info)
                containers.append(cont_info)

                amount = -1 * (cont_info["resources"]["cpu"]["current"] - cont_info["resources"]["cpu"]["min"])
                if amount != 0:
                    request = guardian.generate_request(cont_info, amount, "cpu")
                    print(request)
                    requests.append(request)

        self.couchdb_handler.add_requests(requests)

    def raise_restriction(self, user):
        user["accounting"]["restricted"] = False
        # Set containers to guarded and generate petitions to increase the resources for containers, at least until the Guardian picks up
        apps = user["applications"]
        containers = list()
        requests = list()
        guardian = Guardian()
        for app_name in apps:
            app_info = self.couchdb_handler.get_structure(app_name)
            for cont_name in app_info["containers"]:
                cont_info = self.couchdb_handler.get_structure(cont_name)
                cont_info["guard"] = True
                self.couchdb_handler.update_structure(cont_info)
                containers.append(cont_info)

                amount = int(0.5 * (cont_info["resources"]["cpu"]["max"] - cont_info["resources"]["cpu"]["current"]))
                if amount > 0:
                    request = guardian.generate_request(cont_info, amount, "cpu")
                    print(request)
                    requests.append(request)

        self.couchdb_handler.add_requests(requests)

    def check_credit(self, user):
        user_name = user["name"]
        user_restricted = user["accounting"]["restricted"]
        user_credit = user["accounting"]["credit"]
        if user_restricted and user_credit <= 0:
            log_warning("User {0} is restricted, but still does not have enough credit".format(user_name), self.debug)
        elif not user_restricted and user_credit <= 0:
            log_warning("User {0} is not restricted, but does not have enough credit, restricting".format(user_name), self.debug)
            self.restrict_user(user)
        elif user_restricted and user_credit > 0:
            log_warning("User {0} is restricted, but has enough credit now, raising restriction".format(user_name), self.debug)
            self.raise_restriction(user)
        elif not user_restricted and user_credit > 0:
            log_warning("User {0} is not restricted and has enough credit".format(user_name), self.debug)

    def manage_thread(self, users):
        users_wallets = self.get_users_wallets()

        for u in users:
            log_info("Processing User {0}".format(u["name"]), self.debug)

            # Refresh the info regarding credit and coins
            if u["name"] in users_wallets:
                log_info("User {0} has {1} GRC".format(u["name"], users_wallets[u["name"]]), self.debug)
                self.compute_credit_cpu(u, users_wallets)
            else:
                log_warning("User {0} does not have a registered wallet", self.debug)
                self.couchdb_handler.update_user(u)
                continue

            # Refresh the information
            self.compute_consumed_cpu(u)

            # Rebase the counters
            self.rebase_counters(u)

            # Check that every user has enough credit
            self.check_credit(u)

            self.couchdb_handler.update_user(u)
            log_info("Updated User {0} (cpu)".format(u["name"]), self.debug)

    def compute_credit_cpu(self, user, users_credits):
        user_name = user["name"]
        if user_name not in users_credits:
            log_warning("User {0} does not have a wallet".format(user_name), self.debug)
        else:
            user["accounting"]["credit"] = self.coins_credit_ratio * users_credits[user_name]
            user["accounting"]["coins"] = users_credits[user_name]

    def compute_consumed_cpu(self, user):
        cpu_consumed = user["cpu"]["used"] / 100  # Convert shares to vcores
        if cpu_consumed > self.threshold:
            user["accounting"]["consumed"] += cpu_consumed * self.polling_frequency
            user["accounting"]["consumed"] = round(user["accounting"]["consumed"], 2)

    def manage(self, ):
        myConfig = MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

        while True:
            # Get service info
            service = get_service(self.couchdb_handler, SERVICE_NAME)

            # Heartbeat
            beat(self.couchdb_handler, SERVICE_NAME)

            # CONFIG
            myConfig.set_config(service["config"])
            self.debug = myConfig.get_value("DEBUG")
            debug = self.debug
            self.polling_frequency = myConfig.get_value("POLLING_FREQUENCY")
            self.grc_user = myConfig.get_value("GRIDCOIN_RPC_USER")
            self.grc_pass = myConfig.get_value("GRIDCOIN_RPC_PASS")
            self.grc_ip = myConfig.get_value("GRIDCOIN_RPC_IP")
            self.grc_port = myConfig.get_value("GRIDCOIN_RPC_PORT")
            self.coins_credit_ratio = myConfig.get_value("COINS_TO_CREDIT_RATIO")
            SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")
            self.threshold = myConfig.get_value("THRESHOLD")

            t0 = start_epoch(self.debug)

            log_info("Config is as follows:", debug)
            log_info(".............................................", debug)
            log_info("Polling frequency -> {0}".format(self.polling_frequency), debug)
            log_info("GRC user -> {0}".format(self.grc_user), debug)
            log_info("GRC password -> {0}".format(self.grc_pass), debug)
            log_info("GRC ip -> {0}".format(self.grc_ip), debug)
            log_info("GRC port -> {0}".format(self.grc_port), debug)
            log_info(".............................................", debug)

            self.config_grc_connection()
            if not self.test_grc_connection():
                log_error("GRC connection failed", self.debug)

            thread = None
            if SERVICE_IS_ACTIVATED:
                users = self.couchdb_handler.get_users()
                users = [u for u in users if u["accounting"]["active"]]
                if not users:
                    log_info("No users to process", debug)
                    time.sleep(self.polling_frequency)
                    end_epoch(self.debug, self.polling_frequency, t0)
                    continue
                else:
                    thread = Thread(target=self.manage_thread, args=(users,))
                    thread.start()
            else:
                log_warning("CreditManager is not activated", debug)

            time.sleep(self.polling_frequency)

            wait_operation_thread(thread, debug)
            log_info("Credit management processed", debug)

            end_epoch(self.debug, self.polling_frequency, t0)


def main():
    try:
        checker = CreditManager()
        checker.manage()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

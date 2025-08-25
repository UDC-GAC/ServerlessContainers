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

import time
import traceback

import src.Guardian.Guardian
import src.MyUtils.MyUtils as utils
from src.MyUtils.ConfigValidator import ConfigValidator
from src.Service.Service import Service

CONFIG_DEFAULT_VALUES = {"DELAY": 120, "POLLING_FREQUENCY": 0, "DATABASES": ["events", "requests", "services", "structures", "limits"], "DEBUG": True, "ACTIVE": True}


class SanityChecker(Service):

    def __init__(self):
        super().__init__("sanity_checker", ConfigValidator(min_frequency=0), CONFIG_DEFAULT_VALUES, sleep_attr="polling_frequency")
        self.delay, self.debug = None, None

    def compact_databases(self):
        try:
            compacted_dbs = list()
            for db in self.databases:
                success = self.couchdb_handler.compact_database(db)
                if success:
                    compacted_dbs.append(db)
                else:
                    utils.log_warning("Database {0} could not be compacted".format(db), self.debug)
            utils.log_info("Databases {0} have been compacted".format(str(compacted_dbs)), self.debug)
        except Exception as e:
            utils.log_error(
                "Error doing database compaction: {0} {1}".format(str(e), str(traceback.format_exc())), self.debug)

    def check_unstable_configuration(self):
        try:
            utils.log_info("Checking for invalid configuration", self.debug)
            service = utils.get_service(self.couchdb_handler, "guardian")
            guardian_configuration = service["config"]
            event_timeout = utils.get_config_value(guardian_configuration, src.Guardian.Guardian.CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
            window_timelapse = utils.get_config_value(guardian_configuration, src.Guardian.Guardian.CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

            rules = self.couchdb_handler.get_rules()
            for rule in rules:
                if "generates" in rule and rule["generates"] == "requests" and rule["active"]:
                    event_count = int(rule["events_to_remove"])
                    event_window_time_to_trigger = window_timelapse * (event_count)
                    # Leave a slight buffer time to account for window times skewness
                    if event_window_time_to_trigger > event_timeout:
                        utils.log_error(
                            "Rule: '{0}' could never be activated -> guardian event timeout: '{1}', number of events".format(
                                rule["name"], str(event_timeout)) +
                            " required to trigger the rule: '{0}' and guardian polling time: '{1}'".format(
                                str(event_count), str(window_timelapse)), self.debug)
        except Exception as e:
            utils.log_error(
                "Error doing configuration check up: {0} {1}".format(str(e), str(traceback.format_exc())), self.debug)

    def work(self, ):
        self.compact_databases()
        self.check_unstable_configuration()
        # check_core_mapping()
        utils.log_info("Sanity checked", self.debug)
        utils.log_info(".............................................", self.debug)

        time_waited = 0
        heartbeat_delay = 10  # seconds
        while time_waited < self.delay:
            # Heartbeat
            utils.beat(self.couchdb_handler, self.service_name)
            time.sleep(heartbeat_delay)
            time_waited += heartbeat_delay

        return None

    def check_sanity(self):
        self.run_loop()


def main():
    try:
        sanity_checker = SanityChecker()
        sanity_checker.check_sanity()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

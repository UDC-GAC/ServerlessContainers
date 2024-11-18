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

import src.Guardian.Guardian
import src.MyUtils.MyUtils as MyUtils
import src.StateDatabase.couchdb as couchDB

db_handler = couchDB.CouchDBServer()
rescaler_http_session = requests.Session()
SERVICE_NAME = "sanity_checker"
debug = True
CONFIG_DEFAULT_VALUES = {"DELAY": 120, "DEBUG": True}
DATABASES = ["events", "requests", "services", "structures", "limits"]


def compact_databases():
    try:
        compacted_dbs = list()
        for db in DATABASES:
            success = db_handler.compact_database(db)
            if success:
                compacted_dbs.append(db)
            else:
                MyUtils.log_warning("Database {0} could not be compacted".format(db), debug)
        MyUtils.log_info("Databases {0} have been compacted".format(str(compacted_dbs)), debug)
    except Exception as e:
        MyUtils.log_error(
            "Error doing database compaction: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def check_unstable_configuration():
    try:
        MyUtils.log_info("Checking for invalid configuration", debug)
        service = MyUtils.get_service(db_handler, "guardian")
        guardian_configuration = service["config"]
        event_timeout = MyUtils.get_config_value(guardian_configuration, src.Guardian.Guardian.CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
        window_timelapse = MyUtils.get_config_value(guardian_configuration, src.Guardian.Guardian.CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

        rules = db_handler.get_rules()
        for rule in rules:
            if "generates" in rule and rule["generates"] == "requests" and rule["active"]:
                event_count = int(rule["events_to_remove"])
                event_window_time_to_trigger = window_timelapse * (event_count)
                # Leave a slight buffer time to account for window times skewness
                if event_window_time_to_trigger > event_timeout:
                    MyUtils.log_error(
                        "Rule: '{0}' could never be activated -> guardian event timeout: '{1}', number of events".format(
                            rule["name"], str(event_timeout)) +
                        " required to trigger the rule: '{0}' and guardian polling time: '{1}'".format(
                            str(event_count), str(window_timelapse)), debug)
    except Exception as e:
        MyUtils.log_error(
            "Error doing configuration check up: {0} {1}".format(str(e), str(traceback.format_exc())), debug)


def check_sanity():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=MyUtils.LOGGING_FORMAT, datefmt=MyUtils.LOGGING_DATEFMT)
    global debug
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
        delay = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DELAY")

        compact_databases()
        check_unstable_configuration()
        # check_core_mapping()
        MyUtils.log_info("Sanity checked", debug)

        time_waited = 0
        heartbeat_delay = 10  # seconds

        while time_waited < delay:
            # Heartbeat
            MyUtils.beat(db_handler, SERVICE_NAME)
            time.sleep(heartbeat_delay)
            time_waited += heartbeat_delay


def main():
    try:
        check_sanity()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

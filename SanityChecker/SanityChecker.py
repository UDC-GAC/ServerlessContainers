# /usr/bin/python
from __future__ import print_function

import MyUtils.MyUtils as MyUtils
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB

db_handler = couchDB.CouchDBServer()
SERVICE_NAME = "sanity_checker"
debug = True
CONFIG_DEFAULT_VALUES = {"DELAY": 120, "DEBUG": True}
DATABASES = ["events", "requests", "services", "structures", "limits"]


def compact_databases():
    compacted_dbs = list()
    for db in DATABASES:
        success = db_handler.compact_database(db)
        if success:
            compacted_dbs.append(db)
        else:
            MyUtils.logging_warning("Database {0} could not be compacted".format(db), debug)
    MyUtils.logging_info("Databases {0} have been compacted".format(str(compacted_dbs)), debug)


def check_unstable_configuration():
    MyUtils.logging_info("Checking for invalid configuration", debug)
    service = MyUtils.get_service(db_handler, "guardian")
    guardian_configuration = service["config"]
    event_timeout = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "EVENT_TIMEOUT")
    window_timelapse = MyUtils.get_config_value(guardian_configuration, CONFIG_DEFAULT_VALUES, "WINDOW_TIMELAPSE")

    rules = db_handler.get_rules()
    for rule in rules:
        if rule["generates"] == "requests":
            event_count = int(rule["events_to_remove"])
            event_window_time_to_trigger = window_timelapse * (event_count + 1)
            # Leave a slight buffer time to account for window times skewness
            if event_window_time_to_trigger > event_timeout:
                MyUtils.logging_warning(
                    "Rule: '{0}' could never be activated -> guardian event timeout: '{1}', number of events" +
                    " required to trigger the rule: '{2}' and guardian polling time: '{3}'".format(
                        rule["name"], str(event_timeout), str(event_count), str(window_timelapse)), debug)


def check_sanity():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
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
        MyUtils.logging_info("Sanity checked at {0}".format(MyUtils.get_time_now_string()), debug)

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
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

# /usr/bin/python
from __future__ import print_function

from threading import Thread

import requests
import json
import time
import traceback
import logging

import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as opentsdb
import src.MyUtils.MyUtils as MyUtils

db_handler = couchdb.CouchDBServer()
opentsdb_handler = opentsdb.OpenTSDBServer()
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
OPENTSDB_STORED_VALUES_AS_NULL = 0
SERVICE_NAME = "database_snapshoter"
MAX_FAIL_NUM = 5
debug = True

PERSIST_METRICS = ["max", "min", "upper", "lower", "current", "usage", "fixed", "shares"]
PERSIST_CONFIG_SERVICES = [
    {"name": "guardian",
     "parameters": [
         ("WINDOW_DELAY", "conf.guardian.window_delay"),
         ("EVENT_TIMEOUT", "conf.guardian.event_timeout"),
         ("WINDOW_TIMELAPSE", "conf.guardian.window_timelapse")
     ]},
    {"name": "scaler",
     "parameters": [
         ("REQUEST_TIMEOUT", "conf.scaler.request_timeout"),
         ("POLLING_FREQUENCY", "conf.scaler.polling_frequency")
     ]}
]


def translate_structure_doc_to_timeseries(doc):
    try:
        struct_name = doc["name"]
        timestamp = int(time.time())

        timeseries_list = list()
        for resource in doc["resources"]:
            for doc_metric in doc["resources"][resource]:
                if doc_metric in PERSIST_METRICS and doc_metric in doc["resources"][resource]:
                    value = doc["resources"][resource][doc_metric]
                    if value or value == 0:
                        metric = ".".join([doc["type"], resource, doc_metric])
                        timeseries = dict(metric=metric, value=value, timestamp=timestamp,
                                          tags={"structure": struct_name})
                        timeseries_list.append(timeseries)
                    else:
                        MyUtils.log_error(
                            "Error with document: {0}, doc metric {1} has null value '{2}', assuming a value of '{3}'".format(
                                str(doc), doc_metric, value, OPENTSDB_STORED_VALUES_AS_NULL), debug)

        return timeseries_list
    except (ValueError, KeyError) as e:
        MyUtils.log_error("Error {0} {1} with document: {2} ".format(str(e), str(traceback.format_exc()), str(doc)),
                          debug)
        raise


def get_limits():
    docs = list()
    # Remote database operation
    for limit in db_handler.get_all_limits():
        docs += translate_structure_doc_to_timeseries(limit)
    return docs


def get_structures():
    docs = list()
    # Remote database operation
    for structure in db_handler.get_structures():
        docs += translate_structure_doc_to_timeseries(structure)
    return docs


def get_configs():
    docs = list()
    # Remote database operation
    services = db_handler.get_services()
    for service in PERSIST_CONFIG_SERVICES:
        service_name = service["name"]
        for s in services:
            if service_name == s["name"]:
                service_doc = s
                break
        for parameter in service["parameters"]:
            database_key_name, timeseries_metric_name = parameter
            value = service_doc["config"][database_key_name]
            timestamp = int(time.time())
            timeseries = dict(metric=timeseries_metric_name, value=value, timestamp=timestamp,
                              tags={"service": service_name})
            docs.append(timeseries)
    return docs


# TODO These methods could be better implemented through function passing
def persist_limits():
    t0 = time.time()
    docs = list()
    try:
        docs += get_limits()
    except (requests.exceptions.HTTPError, KeyError, ValueError):
        # An error might have been thrown because database was recently updated or created
        MyUtils.log_warning("Couldn't retrieve limits info.", debug)
    t1 = time.time()
    MyUtils.log_info("It took {0} seconds to get the limits".format(str("%.2f" % (t1 - t0))), debug)
    send_data(docs, "limits")


def persist_structures():
    t0 = time.time()
    docs = list()
    try:
        docs += get_structures()
    except (requests.exceptions.HTTPError, KeyError, ValueError):
        # An error might have been thrown because database was recently updated or created
        MyUtils.log_warning("Couldn't retrieve structure info.", debug)
    t1 = time.time()
    MyUtils.log_info("It took {0} seconds to get the structures".format(str("%.2f" % (t1 - t0))), debug)
    send_data(docs, "structures")


def persist_config():
    t0 = time.time()
    docs = list()
    try:
        docs += get_configs()
    except (requests.exceptions.HTTPError, KeyError, ValueError):
        # An error might have been thrown because database was recently updated or created
        MyUtils.log_warning("Couldn't retrieve config info.", debug)
    t1 = time.time()
    MyUtils.log_info("It took {0} seconds to get the config documents".format(str("%.2f" % (t1 - t0))), debug)
    send_data(docs, "config")


def send_data(docs, doc_type):
    if docs:
        # Remote database operation
        t0 = time.time()
        success, info = opentsdb_handler.send_json_documents(docs)
        if not success:
            MyUtils.log_error("Couldn't properly post documents, error : {0}".format(json.dumps(info["error"])),
                              debug)
        else:
            MyUtils.log_info(
                "Post was done at: {0} with {1} documents".format(time.strftime("%D %H:%M:%S", time.localtime()),
                                                                  str(len(docs))), debug)
            t1 = time.time()
            #MyUtils.log_info("It took {0} seconds to send all the {1} documents".format(
            #    str("%.2f" % (t1 - t0)), doc_type), debug)
    else:
        MyUtils.log_warning("Couldn't retrieve any info.", debug)


def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    fail_count = 0
    global debug
    while True:

        # Get service info
        # Remote database operation
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        # Remote database operation
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        threads = list()
        t = Thread(target=persist_limits, args=())
        t.start()
        threads.append(t)
        t = Thread(target=persist_structures, args=())
        t.start()
        threads.append(t)
        t = Thread(target=persist_config, args=())
        t.start()
        threads.append(t)

        for t in threads:
            t.join()

        MyUtils.log_info("Epoch processed at {0}".format(MyUtils.get_time_now_string()), debug)
        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

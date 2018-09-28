# /usr/bin/python
from __future__ import print_function
import requests
import json
import time
import traceback
import logging
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as MyUtils
from src.pipelines import send_to_OpenTSDB as OpenTSDB_sender

db_handler = couchDB.CouchDBServer()
opentsdb_Session = requests.Session()
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
OPENTSDB_STORED_VALUES_AS_NULL = 0
SERVICE_NAME = "database_snapshoter"
MAX_FAIL_NUM = 5
debug = True

PERSIST_METRICS = ["max", "min", "upper", "lower", "current", "usage", "fixed"]


def translate_doc_to_timeseries(doc):
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
                        timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags={"structure": struct_name})
                        timeseries_list.append(timeseries)
                    else:
                        MyUtils.logging_error(
                            "Error with document: {0}, doc metric {1} has null value '{2}', assuming a value of '{3}'".format(str(doc),doc_metric,value,OPENTSDB_STORED_VALUES_AS_NULL), debug)

        return timeseries_list
    except (ValueError, KeyError) as e:
        MyUtils.logging_error("Error {0} {1} with document: {2} ".format(str(e), str(traceback.format_exc()), str(doc)),
                              debug)
        raise


def get_limits():
    docs = list()
    for limit in db_handler.get_all_limits():
        docs += translate_doc_to_timeseries(limit)
    return docs


def get_structures():
    docs = list()
    for structure in db_handler.get_structures(subtype="container"):
        docs += translate_doc_to_timeseries(structure)
    for application in db_handler.get_structures(subtype="application"):
        docs += translate_doc_to_timeseries(application)
    return docs


def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    fail_count = 0
    global debug
    while True:

        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)

        # CONFIG
        config = service["config"]
        polling_frequency = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
        debug = MyUtils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")

        # Get the data
        docs = list()
        try:
            docs += get_limits()
        except (requests.exceptions.HTTPError, KeyError, ValueError):
            # An error might have been thrown because database was recently updated or created
            MyUtils.logging_warning("Couldn't retrieve limits info.", debug)

        try:
            docs += get_structures()
        except (requests.exceptions.HTTPError, KeyError, ValueError):
            # An error might have been thrown because database was recently updated or created
            MyUtils.logging_warning("Couldn't retrieve structure info.", debug)

        # Send the data
        if docs != list():
            success, info = OpenTSDB_sender.send_json_documents(docs, opentsdb_Session)
            if not success:
                MyUtils.logging_error("Couldn't properly post documents, error : {0}".format(json.dumps(info["error"])),
                                      debug)
                fail_count += 1
            else:
                MyUtils.logging_info(
                    "Post was done at: {0} with {1} documents".format(time.strftime("%D %H:%M:%S", time.localtime()),
                                                                      str(len(docs))), debug)
                fail_count = 0
        else:
            MyUtils.logging_warning("Couldn't retrieve any info.", debug)

        # If too many errors, abort
        if fail_count >= MAX_FAIL_NUM:
            MyUtils.logging_error("TSDB SENDER failed for {0} times, exiting.".format(str(fail_count)), debug)
            exit(1)

        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception as e:
        MyUtils.logging_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

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
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
SERVICE_NAME = "database_snapshoter"
MAX_FAIL_NUM = 5
debug = True

PERSIST_METRICS = ["max", "min", "upper", "lower", "current"]

def translate_doc_to_timeseries(doc):
    try:
        struct_name = doc["name"]
        timestamp = int(time.time())

        timeseries_list = list()
        for resource in doc["resources"]:
            for doc_metric in doc["resources"][resource]:
                if doc_metric in PERSIST_METRICS:
                    value = doc["resources"][resource][doc_metric]
                    metric = doc["type"] + "." + resource + "." + doc_metric
                    timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags={"structure": struct_name})
                    timeseries_list.append(timeseries)

        return timeseries_list
    except (ValueError, KeyError) as e:
        MyUtils.logging_error("Error " + str(e) + " " + str(traceback.format_exc() + " with document: " + str(doc)),
                              debug)
        raise


def get_limits():
    docs = list()
    for limit in db_handler.get_all_database_docs("limits"):
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
            success, info = OpenTSDB_sender.send_json_documents(docs)
            if not success:
                MyUtils.logging_error("Couldn't properly post documents, error : ", debug)
                MyUtils.logging_error(json.dumps(info["error"]), debug)
                fail_count += 1
            else:
                MyUtils.logging_info(
                    "Post was done at: " + time.strftime("%D %H:%M:%S", time.localtime()) + " with " + str(
                        len(docs)) + " documents", debug)
                fail_count = 0
        else:
            MyUtils.logging_warning("Couldn't retrieve any info.", debug)

        # If too many errors, abort
        if fail_count >= MAX_FAIL_NUM:
            MyUtils.logging_error("TSDB SENDER failed for " + str(fail_count) + " times, exiting.", debug)
            exit(1)

        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception as e:
        MyUtils.logging_error(str(e) + " " + str(traceback.format_exc()), debug=True)


if __name__ == "__main__":
    main()

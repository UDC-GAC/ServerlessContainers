# Copyright (c) 2019 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
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

from threading import Thread

import requests
import json
import time
import traceback
import logging

import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as opentsdb
from src.MyUtils import MyUtils
from src.MyUtils.MyUtils import MyConfig

db_handler = couchdb.CouchDBServer()
opentsdb_handler = opentsdb.OpenTSDBServer()
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 10, "DEBUG": True}
OPENTSDB_STORED_VALUES_AS_NULL = 0
SERVICE_NAME = "database_snapshoter"
MAX_FAIL_NUM = 5
debug = True

PERSIST_METRICS = ["max", "min", "upper", "lower", "current", "usage", "fixed", "shares"]
PERSIST_CONFIG_SERVICES_NAMES = ["guardian", "scaler"]
PERSIST_CONFIG_SERVICES_DOCS = {
    "guardian": [
        ("WINDOW_DELAY", "conf.guardian.window_delay"),
        ("EVENT_TIMEOUT", "conf.guardian.event_timeout"),
        ("WINDOW_TIMELAPSE", "conf.guardian.window_timelapse")
    ],
    "scaler": [
        ("REQUEST_TIMEOUT", "conf.scaler.request_timeout"),
        ("POLLING_FREQUENCY", "conf.scaler.polling_frequency")
    ]
}


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


def get_users():
    docs = list()
    # Remote database operation
    for user in db_handler.get_users():
        timestamp = int(time.time())
        for submetric in ["used", "max", "usage", "current"]:
            timeseries = dict(metric="user.energy.{0}".format(submetric),
                              value=user["energy"][submetric],
                              timestamp=timestamp,
                              tags={"user": user["name"]})
            docs.append(timeseries)
    return docs


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
    services = db_handler.get_services()  # Remote database operation
    filtered_services = [s for s in services if s["name"] in PERSIST_CONFIG_SERVICES_NAMES]
    for service in filtered_services:
        for parameter in PERSIST_CONFIG_SERVICES_DOCS[service["name"]]:
            database_key_name, timeseries_metric_name = parameter
            timeseries = dict(metric=timeseries_metric_name,
                              value=service["config"][database_key_name],
                              timestamp=int(time.time()),
                              tags={"service": service["name"]})
            docs.append(timeseries)
    return docs


funct_map = {"users": get_users,
             "limits": get_limits,
             "structures": get_structures,
             "configs": get_configs}


def persist_docs(funct):
    t0 = time.time()
    docs = list()
    try:
        docs += funct_map[funct]()
    except (requests.exceptions.HTTPError, KeyError, ValueError) as e:
        # An error might have been thrown because database was recently updated or created
        MyUtils.log_warning("Couldn't retrieve {0} info, error {1}.".format(funct, str(e)), debug)
    t1 = time.time()
    MyUtils.log_info("It took {0} seconds to get the {1} info".format(str("%.2f" % (t1 - t0)), funct), debug)
    send_data(docs)


def send_data(docs):
    if docs:
        # Remote database operation
        success, info = opentsdb_handler.send_json_documents(docs)
        if not success:
            MyUtils.log_error("Couldn't properly post documents, error : {0}".format(json.dumps(info["error"])),
                              debug)
        else:
            MyUtils.log_info(
                "Post was done at: {0} with {1} documents".format(time.strftime("%D %H:%M:%S", time.localtime()),
                                                                  str(len(docs))), debug)
    else:
        MyUtils.log_warning("Couldn't retrieve any info.", debug)


def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)
    global debug
    myConfig = MyConfig(CONFIG_DEFAULT_VALUES)
    while True:
        # Get service info
        service = MyUtils.get_service(db_handler, SERVICE_NAME)  # Remote database operation

        # Heartbeat
        MyUtils.beat(db_handler, SERVICE_NAME)  # Remote database operation

        # CONFIG
        myConfig.set_config(service["config"])
        polling_frequency = myConfig.get_config_value("POLLING_FREQUENCY")
        debug = myConfig.get_config_value("DEBUG")

        for docType in ["limits", "structures", "users", "configs"]:
            persist_docs(docType)

        MyUtils.log_info("Epoch processed at {0}".format(MyUtils.get_time_now_string()), debug)
        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception as e:
        MyUtils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

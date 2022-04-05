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
import json
import time
import traceback
import logging

import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as opentsdb


from src.MyUtils.MyUtils import MyConfig, log_error, get_service, beat, log_info, log_warning

db_handler = couchdb.CouchDBServer()
opentsdb_handler = opentsdb.OpenTSDBServer()
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "DEBUG": True, "DOCUMENTS_PERSISTED": ["limits", "structures", "users", "configs"] ,"ACTIVE": True}
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
                        log_error(
                            "Error with document: {0}, doc metric {1} has null value '{2}', assuming a value of '{3}'".format(
                                str(doc), doc_metric, value, OPENTSDB_STORED_VALUES_AS_NULL), debug)

        return timeseries_list
    except (ValueError, KeyError) as e:
        log_error("Error {0} {1} with document: {2} ".format(str(e), str(traceback.format_exc()), str(doc)), debug)
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

def get_data(funct):
    docs = list()
    try:
        docs += funct_map[funct]()
    except (requests.exceptions.HTTPError, KeyError, ValueError) as e:
        # An error might have been thrown because database was recently updated or created
        log_warning("Couldn't retrieve {0} info, error {1}.".format(funct, str(e)), debug)
    return docs

def send_data(docs):
    num_sent_docs = 0
    if docs:
        # Remote database operation
        success, info = opentsdb_handler.send_json_documents(docs)
        if not success:
            log_error("Couldn't properly post documents, error : {0}".format(json.dumps(info["error"])), debug)
        else:
            num_sent_docs = len(docs)
    return num_sent_docs

def persist_docs(funct):

    t0 = time.time()
    docs = get_data(funct)
    t1 = time.time()

    if docs:
        log_info("It took {0} seconds to get {1} info".format(str("%.2f" % (t1 - t0)), funct), debug)
        num_docs = send_data(docs)
        t2 = time.time()
        if num_docs > 0:
            log_info("It took {0} seconds to send {1} info".format(str("%.2f" % (t2 - t1)),funct), debug)
            log_info("Post was done with {0} documents of '{1}'".format(str(num_docs), funct), debug)


def invalid_conf(config):
    # TODO THis code is duplicated on the structures and database snapshoters
    for key, num in [("POLLING_FREQUENCY",config.get_value("POLLING_FREQUENCY"))]:
        if num < 3:
            return True, "Configuration item '{0}' with a value of '{1}' is likely invalid".format(key, num)
    return False, ""

def persist():
    logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO)

    global debug

    myConfig = MyConfig(CONFIG_DEFAULT_VALUES)

    while True:
        log_info("----------------------", debug)
        log_info("Starting Epoch", debug)
        t0 = time.time()

        # Get service info
        service = get_service(db_handler, SERVICE_NAME)  # Remote database operation

        # Heartbeat
        beat(db_handler, SERVICE_NAME)  # Remote database operation

        # CONFIG
        myConfig.set_config(service["config"])
        polling_frequency = myConfig.get_value("POLLING_FREQUENCY")
        debug = myConfig.get_value("DEBUG")
        documents_persisted = myConfig.get_value("DOCUMENTS_PERSISTED")
        SERVICE_IS_ACTIVATED = myConfig.get_value("ACTIVE")

        log_info("Config is as follows:", debug)
        log_info(".............................................", debug)
        log_info("Polling frequency -> {0}".format(polling_frequency), debug)
        log_info("Documents to be persisted are -> {0}".format(documents_persisted), debug)
        log_info(".............................................", debug)

        ## CHECK INVALID CONFIG ##
        # TODO THis code is duplicated on the structures and database snapshoters
        invalid, message = invalid_conf(myConfig)
        if invalid:
            log_error(message, debug)
            time.sleep(polling_frequency)
            if polling_frequency < 4:
                log_error("Polling frequency is too short, replacing with DEFAULT value '{0}'".format(CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]), debug)
                polling_frequency = CONFIG_DEFAULT_VALUES["POLLING_FREQUENCY"]

            log_info("----------------------\n", debug)
            time.sleep(polling_frequency)
            continue

        if SERVICE_IS_ACTIVATED:
            for docType in documents_persisted:
                persist_docs(docType)
        else:
            log_warning("Database snapshoter is not activated, will not do anything", debug)

        t1 = time.time()
        log_info("Epoch processed in {0} seconds ".format("%.2f" % (t1 - t0)), debug)
        log_info("----------------------\n", debug)

        time.sleep(polling_frequency)


def main():
    try:
        persist()
    except Exception as e:
        log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

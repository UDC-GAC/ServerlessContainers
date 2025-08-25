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

import src.MyUtils.MyUtils as utils
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.opentsdb as opentsdb
from src.MyUtils.ConfigValidator import ConfigValidator

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

CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY": 5, "DOCUMENTS_PERSISTED": ["limits", "structures", "users", "configs"],
                         "SERVICES_PERSISTED": ["guardian", "scaler"],
                         "FIELDS_PERSISTED": ["max", "min", "upper", "lower", "current", "usage", "fixed", "shares"],
                         "DEBUG": True, "ACTIVE": True}
SERVICE_NAME = "database_snapshoter"


class DatabaseSnapshoter:

    def __init__(self):
        self.config_validator = ConfigValidator(min_frequency=3)
        self.couchdb_handler = couchdb.CouchDBServer()
        self.opentsdb_handler = opentsdb.OpenTSDBServer()
        self.NO_METRIC_DATA_DEFAULT_VALUE = self.opentsdb_handler.NO_METRIC_DATA_DEFAULT_VALUE
        self.polling_frequency, self.documents_persisted, self.services_persisted = None, None, None
        self.fields_persisted, self.debug, self.active = None, None, None

    def translate_structure_doc_to_timeseries(self, doc):
        try:
            struct_name = doc["name"]
            timestamp = int(time.time())
            timeseries_list = []
            for resource in doc["resources"]:
                for doc_field in self.fields_persisted:
                    value = doc["resources"][resource].get(doc_field, None)
                    if value is not None:
                        if value != self.NO_METRIC_DATA_DEFAULT_VALUE:
                            metric = ".".join([doc["type"], resource, doc_field])
                            timeseries = dict(metric=metric, value=value, timestamp=timestamp, tags={"structure": struct_name})
                            timeseries_list.append(timeseries)
                        else:
                            utils.log_error("Document for structure {0} has a null value in field '{1}' ('{2}')".format(struct_name, doc_field, value), self.debug)

            return timeseries_list
        except (ValueError, KeyError) as e:
            utils.log_error("Error {0} {1} with document: {2} ".format(str(e), str(traceback.format_exc()), str(doc)), self.debug)
            raise e

    def get_users(self, ):
        docs = list()
        # Remote database operation
        for user in self.couchdb_handler.get_users():
            timestamp = int(time.time())
            for submetric in ["used", "max", "usage", "current"]:
                timeseries = dict(metric="user.energy.{0}".format(submetric),
                                  value=user["energy"][submetric],
                                  timestamp=timestamp,
                                  tags={"user": user["name"]})
                docs.append(timeseries)
        return docs

    def get_limits(self, ):
        docs = list()
        # Remote database operation
        for limit in self.couchdb_handler.get_all_limits():
            docs += self.translate_structure_doc_to_timeseries(limit)
        return docs

    def get_structures(self,):
        docs = list()
        # Remote database operation
        for structure in self.couchdb_handler.get_structures():
            docs += self.translate_structure_doc_to_timeseries(structure)
        return docs

    def get_configs(self, ):
        docs = list()
        services = self.couchdb_handler.get_services()  # Remote database operation
        filtered_services = [s for s in services if s["name"] in self.services_persisted]
        for service in filtered_services:
            for parameter in PERSIST_CONFIG_SERVICES_DOCS[service["name"]]:
                database_key_name, timeseries_metric_name = parameter
                if database_key_name in service["config"]:
                    timeseries = dict(metric=timeseries_metric_name,
                                      value=service["config"][database_key_name],
                                      timestamp=int(time.time()),
                                      tags={"service": service["name"]})
                    docs.append(timeseries)
                else:
                    utils.log_warning("Missing config key '{0}' in service '{1}'".format(database_key_name, service["name"]), self.debug)
        return docs

    def get_data(self, doc_type):
        docs = []
        try:
            docs = getattr(self, "get_{0}".format(doc_type))()
        except (requests.exceptions.HTTPError, KeyError, ValueError) as e:
            # An error might have been thrown because database was recently updated or created
            utils.log_warning("Couldn't retrieve {0} info, error {1}.".format(doc_type, str(e)), self.debug)
        return docs

    def send_data(self, docs):
        num_sent_docs = 0
        if docs:
            # Remote database operation
            success, info = self.opentsdb_handler.send_json_documents(docs)
            if not success:
                utils.log_error("Couldn't properly post documents, error : {0}".format(json.dumps(info["error"])), self.debug)
            else:
                num_sent_docs = len(docs)
        return num_sent_docs


    def persist_docs(self, doc_type):
        t0 = time.time()
        docs = self.get_data(doc_type)
        t1 = time.time()

        if docs:
            utils.log_info("It took {0} seconds to get {1} info".format(str("%.2f" % (t1 - t0)), doc_type), self.debug)
            num_docs = self.send_data(docs)
            t2 = time.time()
            if num_docs > 0:
                utils.log_info("It took {0} seconds to send {1} info".format(str("%.2f" % (t2 - t1)), doc_type), self.debug)
                utils.log_info("Post was done with {0} documents of '{1}'".format(str(num_docs), doc_type), self.debug)

    def persist(self,):
        myConfig = utils.MyConfig(CONFIG_DEFAULT_VALUES)
        logging.basicConfig(filename=SERVICE_NAME + '.log', level=logging.INFO, format=utils.LOGGING_FORMAT, datefmt=utils.LOGGING_DATEFMT)

        while True:
            utils.update_service_config(self, SERVICE_NAME, myConfig, self.couchdb_handler)

            t0 = utils.start_epoch(self.debug)

            utils.print_service_config(self, myConfig, self.debug)

            invalid, message = self.config_validator.invalid_conf(myConfig)
            if invalid:
                utils.log_error(message, self.debug)

            if not self.active:
                utils.log_warning("Database snapshoter is not activated", self.debug)

            if self.active and not invalid:
                for doc_type in self.documents_persisted:
                    self.persist_docs(doc_type)

            time.sleep(self.polling_frequency)

            utils.end_epoch(self.debug, self.polling_frequency, t0)


def main():
    try:
        database_snapshoter = DatabaseSnapshoter()
        database_snapshoter.persist()
    except Exception as e:
        utils.log_error("{0} {1}".format(str(e), str(traceback.format_exc())), debug=True)


if __name__ == "__main__":
    main()

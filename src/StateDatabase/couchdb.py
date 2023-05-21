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


import random
import time
import requests
import json
import yaml
import os


class CouchDBServer:
    post_doc_headers = {'content-type': 'application/json'}
    __COUCHDB_URL = "couchdb"
    __COUCHDB_PORT = 5984
    __structures_db_name = "structures"
    __services_db_name = "services"
    __limits_db_name = "limits"
    __rules_db_name = "rules"
    __events_db_name = "events"
    __requests_db_name = "requests"
    __users_db_name = "users"
    __MAX_UPDATE_TRIES = 10
    __DATABASE_TIMEOUT = 10

    def __init__(self, couchdb_url=None, couchdbdb_port=None):

        serverless_path = os.environ['SERVERLESS_PATH']
        config_file = serverless_path + "/services_config.yml"
        with open(config_file, "r") as f:
            config = yaml.load(f, Loader=yaml.FullLoader)

        if not couchdb_url:
            # couchdb_url = self.__COUCHDB_URL
            couchdb_url = config['COUCHDB_URL']
        if not couchdbdb_port:
            # couchdbdb_port = self.__COUCHDB_PORT
            couchdbdb_port = config['COUCHDB_PORT']
        else:
            try:
                couchdbdb_port = int(couchdbdb_port)
            except ValueError:
                couchdbdb_port = self.__COUCHDB_PORT

        # TODO admin username and password are hard-coded
        self.server = "http://admin:admin@{0}:{1}".format(couchdb_url, str(couchdbdb_port))
        self.session = requests.Session()

    def close_connection(self):
        self.session.close()

    def set_database_name(self, database_type, database_name):
        if database_type == "structures":
            self.__structures_db_name = database_name
        elif database_type == "services":
            self.__services_db_name = database_name
        elif database_type == "limits":
            self.__limits_db_name = database_name
        elif database_type == "rules":
            self.__rules_db_name = database_name
        elif database_type == "events":
            self.__events_db_name = database_name
        elif database_type == "requests":
            self.__requests_db_name = database_name
        elif database_type == "profiles":
            self.__profiles_db_name = database_name
        else:
            pass

    def database_exists(self, database):
        r = self.session.head(self.server + "/" + database)
        return r.status_code == 200

    def create_database(self, database):
        r = self.session.put(self.server + "/" + database)
        if r.status_code != 201:
            r.raise_for_status()
        else:
            return True

    def remove_database(self, database):
        r = self.session.delete(self.server + "/" + database)
        if r.status_code != 200:
            r.raise_for_status()
        else:
            return True

    def compact_database(self, database):
        r = self.session.post(self.server + "/" + database + "/_compact", headers=self.post_doc_headers)
        if r.status_code != 202:
            r.raise_for_status()
        else:
            return json.loads(r.text)["ok"]

    def __get_all_database_docs(self, database):
        # TODO Implement pagination
        docs = list()
        r = self.session.get(self.server + "/" + database + "/_all_docs?include_docs=true",
                             timeout=self.__DATABASE_TIMEOUT)
        if r.status_code != 200:
            r.raise_for_status()
        else:
            rows = json.loads(r.text)["rows"]
            for row in rows:
                docs.append(row["doc"])
            return docs

    # PRIVATE CRUD METHODS #

    # def __delete_doc(self, database, docid, rev):
    #     r = self.session.delete("{0}/{1}/{2}?rev={3}".format(self.server, database, str(docid), str(rev)))
    #     if r.status_code != 200:
    #         r.raise_for_status()
    #     else:
    #         return True

    def __add_doc(self, database, doc):
        r = self.session.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
        if r.status_code != 200:
            r.raise_for_status()
        else:
            return True

    def __add_bulk_docs(self, database, docs):
        docs_data = {"docs": docs}
        r = self.session.post(self.server + "/" + database + "/_bulk_docs", data=json.dumps(docs_data),
                              headers=self.post_doc_headers)
        if r.status_code != 201:
            r.raise_for_status()
        else:
            return True

    def __resilient_delete_doc(self, database, doc, max_tries=10):
        time_backoff_milliseconds = 100
        i = 0
        while i < max_tries:
            i += 1
            r = self.session.delete(
                "{0}/{1}/{2}?rev={3}".format(self.server, database, str(doc["_id"]), str(doc["_rev"])))
            if r.status_code == 200 or r.status_code == 201:
                return True
            elif r.status_code == 409:
                # Conflict error, document may have been updated (e.g., heartbeat of services),
                # update revision and retry after slightly random wait
                time.sleep((time_backoff_milliseconds + random.randint(1, 100)) / 1000)
                matches = self.__find_documents_by_matches(database, {"_id": doc["_id"]})
                if len(matches) > 0:
                    new_doc = matches[0]
                    doc["_rev"] = new_doc["_rev"]
            else:
                r.raise_for_status()
        return False

    def __delete_bulk_docs(self, database, docs):
        for doc in docs:
            doc["_deleted"] = True
        self.__add_bulk_docs(database, docs)

    def __merge(self, input_dict, output_dict):
        for key, value in input_dict.items():
            if isinstance(value, dict):
                # get node or create one
                node = output_dict.setdefault(key, {})
                self.__merge(value, node)
            else:
                output_dict[key] = value

        return output_dict

    def __resilient_update_doc(self, database, doc, previous_tries=0, time_backoff_milliseconds=100, max_tries=20):
        r = self.session.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
        if r.status_code != 200 and r.status_code != 201:
            if r.status_code == 409:
                # Conflict error, document may have been updated (e.g., heartbeat of services),
                # update revision and retry after slightly random wait
                if 0 <= previous_tries < max_tries:
                    time.sleep((time_backoff_milliseconds + random.randint(1, 100)) / 1000)
                    matches = self.__find_documents_by_matches(database, {"_id": doc["_id"]})
                    if len(matches) > 0:
                        new_doc = matches[0]
                        doc["_rev"] = new_doc["_rev"]
                        doc = self.__merge(doc, new_doc)
                        return self.__resilient_update_doc(database, doc, previous_tries=previous_tries + 1,
                                                           max_tries=max_tries)
                    else:
                        return self.__resilient_update_doc(database, doc, previous_tries=previous_tries + 1,
                                                           max_tries=max_tries)
                else:
                    r.raise_for_status()
            elif r.status_code == 404:
                # Database may have been reinitialized (deleted and recreated), wait and retry again
                time.sleep((time_backoff_milliseconds + random.randint(1, 200)) / 1000)
                return self.__resilient_update_doc(database, doc, previous_tries + 1)
            else:
                r.raise_for_status()
        return False

    # TODO This new method should work, test it in isolation and new commit
    # def __resilient_update_doc(self, database, doc, max_tries=10):
    #     time_backoff_milliseconds = 100
    #     tries = 0
    #     while tries < max_tries:
    #         r = self.session.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
    #         if r.status_code == 200 and r.status_code == 201:
    #             return True
    #         elif r.status_code == 409:
    #             # Conflict error, document may have been updated (e.g., heartbeat of services),
    #             # update revision and retry after slightly random wait
    #             time.sleep((time_backoff_milliseconds + random.randint(1, 100)) / 1000)
    #             matches = self.__find_documents_by_matches(database, {"_id": doc["_id"]})
    #             if len(matches) > 0:
    #                 new_doc = matches[0]
    #                 doc["_rev"] = new_doc["_rev"]
    #                 doc = self.__merge(doc, new_doc)
    #         elif r.status_code == 404:
    #             # Database may have been reinitialized (deleted and recreated), wait a little bit longer and retry again
    #             time.sleep((time_backoff_milliseconds + random.randint(1, 200)) / 1000)
    #         else:
    #             r.raise_for_status()
    #     return False

    def __find_documents_by_matches(self, database, selectors):
        # TODO Implement pagination
        query = {"selector": {}, "limit": 50}

        for key in selectors:
            query["selector"][key] = selectors[key]

        req_docs = self.session.post(self.server + "/" + database + "/_find", data=json.dumps(query),
                                     headers={'Content-Type': 'application/json'})
        if req_docs.status_code != 200:
            req_docs.raise_for_status()
        else:
            return req_docs.json()["docs"]

    def __find_document_by_name(self, database, doc_name):
        docs = self.__find_documents_by_matches(database, {"name": doc_name})
        if not docs:
            raise ValueError("Document with name {0} not found in database {1}".format(doc_name, database))
        else:
            # Return the first one as it should only be one
            return dict(docs[0])

    # STRUCTURES #
    def add_structure(self, structure):
        return self.__add_doc(self.__structures_db_name, structure)

    def get_structure(self, structure_name):
        return self.__find_document_by_name(self.__structures_db_name, structure_name)

    def get_structures(self, subtype=None):
        if subtype is None:
            return self.__get_all_database_docs(self.__structures_db_name)
        else:
            return self.__find_documents_by_matches(self.__structures_db_name, {"subtype": subtype})

    def delete_structure(self, structure):
        self.__resilient_delete_doc(self.__structures_db_name, structure)

    def update_structure(self, structure, max_tries=10):
        return self.__resilient_update_doc(self.__structures_db_name, structure, max_tries=max_tries)

    # EVENTS #
    def add_event(self, event):
        self.__add_doc(self.__events_db_name, event)

    def add_events(self, events):
        self.__add_bulk_docs(self.__events_db_name, events)

    def get_events(self, structure):
        return self.__find_documents_by_matches(self.__events_db_name, {"structure": structure["name"]})

    def delete_num_events_by_structure(self, structure, event_name, event_num):
        events = self.__find_documents_by_matches(self.__events_db_name,
                                                  {"structure": structure["name"], "name": event_name})
        event_num = min(len(events), event_num)
        events_to_delete = events[0:event_num]
        self.__delete_bulk_docs(self.__events_db_name, events_to_delete)

    def delete_event(self, event):
        self.__resilient_delete_doc(self.__events_db_name, event)

    def delete_events(self, events):
        self.__delete_bulk_docs(self.__events_db_name, events)

    # LIMITS #
    def add_limit(self, limit):
        return self.__add_doc(self.__limits_db_name, limit)

    def get_all_limits(self):
        return self.__get_all_database_docs(self.__limits_db_name)

    def get_limits(self, structure):
        # Return just the first item, as it should only be one 'limits' document, otherwise raise error
        limits = self.__find_documents_by_matches(self.__limits_db_name, {"name": structure["name"]})
        if not limits:
            raise ValueError("Structure with name {0} has no limits".format(structure["name"]))
        else:
            return limits[0]

    def delete_limit(self, limit):
        self.__resilient_delete_doc(self.__limits_db_name, limit)

    def update_limit(self, limit):
        return self.__resilient_update_doc(self.__limits_db_name, limit)

    # REQUESTS #
    def get_requests(self, structure=None):
        if structure is None:
            return self.__get_all_database_docs(self.__requests_db_name)
        else:
            return self.__find_documents_by_matches(self.__requests_db_name, {"structure": structure["name"]})

    def add_request(self, req):
        self.__add_doc(self.__requests_db_name, req)

    def add_requests(self, reqs):
        self.__add_bulk_docs(self.__requests_db_name, reqs)

    def delete_request(self, request):
        self.__resilient_delete_doc(self.__requests_db_name, request)

    def delete_requests(self, requests):
        self.__delete_bulk_docs(self.__requests_db_name, requests)

    # RULES #
    def add_rule(self, rule):
        return self.__add_doc(self.__rules_db_name, rule)

    def get_rule(self, profile, rule_name):
        rules = self.__find_documents_by_matches(self.__rules_db_name, {"profile": profile, "name": rule_name})
        if not rules:
            raise ValueError("No rules found with the profile '{0}' and name '{1}'".format(profile, rule_name))
        else:
            return rules[0]

    def get_profile_rules(self, profile):
        rules = self.__find_documents_by_matches(self.__rules_db_name, {"profile": profile})
        if not rules:
            raise ValueError("No rules found with the profile '{0}'".format(profile))
        else:
            return rules

    def get_rules(self):
        return self.__get_all_database_docs(self.__rules_db_name)

    def update_rule(self, rule):
        return self.__resilient_update_doc(self.__rules_db_name, rule)

    # USERS #
    def add_user(self, user):
        return self.__add_doc(self.__users_db_name, user)

    def get_users(self):
        return self.__get_all_database_docs(self.__users_db_name)

    def get_user(self, user_name):
        return self.__find_document_by_name(self.__users_db_name, user_name)

    def update_user(self, user):
        return self.__resilient_update_doc(self.__users_db_name, user)

    def delete_user(self, user):
        return self.__resilient_delete_doc(self.__users_db_name, user)

    # SERVICES #
    def get_services(self):
        return self.__get_all_database_docs(self.__services_db_name)

    def get_service(self, service_name):
        return self.__find_document_by_name(self.__services_db_name, service_name)

    def add_service(self, service):
        return self.__add_doc(self.__services_db_name, service)

    def update_service(self, service):
        return self.__resilient_update_doc(self.__services_db_name, service)

    def delete_service(self, service):
        return self.__resilient_delete_doc(self.__services_db_name, service)

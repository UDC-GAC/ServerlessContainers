# /usr/bin/python
import random
import time
import requests
import json


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
    __profiles_db_name = "profiles"
    __MAX_UPDATE_TRIES = 10
    __DATABASE_TIMEOUT = 10

    def __init__(self,  couchdb_url=None, couchdbdb_port=None):
        if not couchdb_url:
            couchdb_url = self.__COUCHDB_URL
        if not couchdbdb_port:
            couchdbdb_port = self.__COUCHDB_PORT
        else:
            try:
                couchdbdb_port = int(couchdbdb_port)
            except ValueError:
                couchdbdb_port = self.__COUCHDB_PORT

        self.server = "http://{0}:{1}".format(couchdb_url, str(couchdbdb_port))
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
        docs = list()
        r = self.session.get(self.server + "/" + database + "/_all_docs", timeout=self.__DATABASE_TIMEOUT)
        if r.status_code != 200:
            r.raise_for_status()
        else:
            rows = json.loads(r.text)["rows"]
            for row in rows:
                req_doc = self.session.get("/".join([self.server, database, row["id"]]))
                docs.append(dict(req_doc.json()))
            return docs

    # PRIVATE CRUD METHODS #

    def __delete_doc(self, database, docid, rev):
        r = self.session.delete("{0}/{1}/{2}?rev={3}".format(self.server, database, str(docid), str(rev)))
        if r.status_code != 200:
            r.raise_for_status()
        else:
            return True

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

    def __resilient_update_doc(self, database, doc, previous_tries=0, time_backoff_milliseconds=1000, max_tries=10):
        r = self.session.post(self.server + "/" + database, data=json.dumps(doc), headers=self.post_doc_headers)
        if r.status_code != 200 and r.status_code != 201:
            if r.status_code == 409:
                # Conflict error, document may have been updated (e.g., heartbeat of services),
                # update revision and retry after slightly random wait
                if 0 <= previous_tries < max_tries:
                    time.sleep((time_backoff_milliseconds + random.randint(1, 20)) / 1000)
                    new_doc = self.__find_documents_by_matches(database, {"_id": doc["_id"]})[0]
                    doc["_rev"] = new_doc["_rev"]
                    doc = self.__merge(doc, new_doc)
                    return self.__resilient_update_doc(database, doc, previous_tries=previous_tries + 1,
                                                       max_tries=max_tries)
                else:
                    r.raise_for_status()
            elif r.status_code == 404:
                # Database may have been reinitialized (deleted and recreated), wait and retry again
                time.sleep((time_backoff_milliseconds + random.randint(1, 100)) / 1000)
                return self.__resilient_update_doc(database, doc, previous_tries + 1)
            else:
                r.raise_for_status()
        else:
            return True

    def __find_documents_by_matches(self, database, selectors):
        query = {"selector": {}}

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
        self.__delete_doc(self.__events_db_name, event["_id"], event["_rev"])

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
        self.__delete_doc(self.__requests_db_name, request["_id"], request["_rev"])

    # RULES #
    def add_rule(self, rule):
        return self.__add_doc(self.__rules_db_name, rule)

    def get_rule(self, rule_name):
        return self.__find_document_by_name(self.__rules_db_name, rule_name)

    def get_rules(self):
        return self.__get_all_database_docs(self.__rules_db_name)

    def update_rule(self, rule):
        return self.__resilient_update_doc(self.__rules_db_name, rule)

    # PROFILES #
    def add_profile(self, profile):
        return self.__add_doc(self.__profiles_db_name, profile)

    def get_profiles(self):
        return self.__get_all_database_docs(self.__profiles_db_name)

    def get_profile(self, profile_name):
        return self.__find_document_by_name(self.__profiles_db_name, profile_name)

    def update_profile(self, profile):
        return self.__resilient_update_doc(self.__profiles_db_name, profile)

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
        return self.__delete_doc(self.__services_db_name, service["_id"], service["_rev"])

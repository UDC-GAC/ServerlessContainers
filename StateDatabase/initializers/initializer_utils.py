# /usr/bin/python
import StateDatabase.couchDB as couchDB
import requests


class CouchDBUtils:

    def __init__(self):
        self.handler = couchDB.CouchDBServer()

    def create_db(self, database):
        print("Creating database: " + database)
        if self.handler.create_database(database):
            print("Database " + database + " created")

    def remove_db(self, database):
        print("Removing database: " + database)
        try:
            if self.handler.remove_database(database):
                print("Database " + database + " removed")
        except requests.exceptions.HTTPError:
            pass

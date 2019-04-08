# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

class CouchDBUtils:

    def __init__(self):
        self.handler = couchDB.CouchDBServer()

    def close_connection(self):
        self.handler.close_connection()

    def create_db(self, database):
        if not self.handler.database_exists(database):
            if self.handler.create_database(database):
                print("Database " + database + " created")
            else:
                print("Database " + database + " couldn't be created")
        else:
            print("Database " + database + "already exists")

    def remove_db(self, database):
        if self.handler.database_exists(database):
            if self.handler.remove_database(database):
                print("Database " + database + " removed")
            else:
                print("Database " + database + " couldn't be removed")
        else:
            print("Database " + database + "doesn't exist")


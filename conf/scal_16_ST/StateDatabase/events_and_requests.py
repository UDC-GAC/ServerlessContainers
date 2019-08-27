# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()

    database = "events"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    database = "requests"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

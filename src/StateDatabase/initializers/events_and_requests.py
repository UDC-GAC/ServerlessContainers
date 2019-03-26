# /usr/bin/python
import AutomaticRescaler.src.StateDatabase.couchdb as couchDB
import AutomaticRescaler.src.StateDatabase.initializers.initializer_utils as CouchDB_Utils


if __name__ == "__main__":
    initializer_utils = CouchDB_Utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()

    database = "events"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    database = "requests"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

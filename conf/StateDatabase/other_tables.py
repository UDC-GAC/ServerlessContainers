# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()

    #tables = ["events", "requests", "rules", "limits", "structures"]
    tables = ["events", "requests", "limits", "structures", "users"]
    for table in tables:
        initializer_utils.remove_db(table)
        initializer_utils.create_db(table)

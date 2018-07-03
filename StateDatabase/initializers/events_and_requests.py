# /usr/bin/python
import StateDatabase.couchDB as couchDB
import StateDatabase.initializers.initializer_utils as CouchDB_Utils

initializer_utils = CouchDB_Utils.CouchDB_Utils()
handler = couchDB.CouchDBServer()

database = "events"
initializer_utils.remove_db(database)
initializer_utils.create_db(database)

database = "requests"
initializer_utils.remove_db(database)
initializer_utils.create_db(database)


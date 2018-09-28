# /usr/bin/python
import StateDatabase.couchDB as couchDB
import StateDatabase.initializers.initializer_utils as CouchDB_Utils

initializer_utils = CouchDB_Utils.CouchDBUtils()
handler = couchDB.CouchDBServer()
database = "profiles"
initializer_utils.remove_db(database)
initializer_utils.create_db(database)

# CREATE PROFILES
if handler.database_exists(database):
    print("Adding {0} documents".format(database))

    small_limit = dict(
        type='profile',
        name="small_limit",
        resources=dict(
            cpu=200,
            mem=8192,
            disk=50,
            net=200,
        )
    )
    handler.add_profile(small_limit)

    medium_limit = dict(
        type='profile',
        name="medium_limit",
        resources=dict(
            cpu=150,
            mem=6144,
            disk=25,
            net=150,
        )
    )
    handler.add_profile(medium_limit)

# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

if __name__ == "__main__":

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "users"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists(database):
        print("Adding {0} documents".format(database))

        user0 = dict(
            type='user',
            name="user0",
            energy=dict(
                max=300,
                used=0
            ),
            clusters=["aux_user0", "pre_user0", "comp_user0"]
        )
        handler.add_user(user0)
# /usr/bin/python
import src.StateDatabase.couchdb as couchdb
import src.StateDatabase.utils as couchdb_utils

if __name__ == "__main__":

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchdb.CouchDBServer()
    database = "users"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists(database):
        print("Adding {0} documents".format(database))

        user0 = dict(
            type="user",
            subtype="user",
            name="user0",
            balancing_method="pair_swapping",
            resources=dict(
                energy=dict(max=100, min=20),
                cpu=dict(max=2000, min=100),
            ),
            clusters=[]
        )
        handler.add_user(user0)

        user1 = dict(
            type='user',
            subtype='user',
            name="user1",
            balancing_method="pair_swapping",
            resources=dict(
                energy=dict(max=100, min=20),
                cpu=dict(max=2000, min=100),
            ),
            clusters=[]
        )
        handler.add_user(user1)

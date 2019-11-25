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
            energy_policy="static",
            energy=dict(
                max=300,
                used=0
            ),
            cpu=dict(
                current=0,
                usage=0
            ),
            clusters=["kafkas_user0", "hibenches_user0", "spark_user0"]
        )
        handler.add_user(user0)

        user1 = dict(
            type='user',
            name="user1",
            energy_policy="static",
            energy=dict(
                max=300,
                used=0
            ),
            cpu=dict(
                current=0,
                usage=0
            ),
            clusters=["kafkas_user1", "hibenches_user1", "spark_user1"]
        )
        handler.add_user(user1)

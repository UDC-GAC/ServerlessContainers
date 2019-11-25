# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["kafka0", "kafka1", "kafka2", "kafka3", "kafka4", "kafka5", "kafka6", "kafka7",
              "hibench0", "hibench1", "hibench2", "hibench3",
              "slave0", "slave1", "slave2", "slave3", "slave4", "slave5", "slave6", "slave7", "slave8", "slave9",
              "slave10", "slave11", "slave12", "slave13", "slave14", "slave15", "slave16", "slave17", "slave18",
              "slave19"
              ]
applications = ["fixwindow_user0"]
#
# base_limits = dict(
#     type='limit',
#     name="base_container",
#     resources=dict(
#         cpu=dict(upper=500, lower=400, boundary=50),
#         mem=dict(upper=44000, lower=40000, boundary=3072),
#         disk=dict(upper=100, lower=20, boundary=10),
#         net=dict(upper=100, lower=20, boundary=10),
#         energy=dict(upper=15, lower=5, boundary=3)
#     )
# )

if __name__ == "__main__":

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "limits"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists("limits"):
        print("Adding 'limits' documents")
        for c in containers:
            container = dict(
                type='limit',
                name=c,
                resources=dict(
                    cpu=dict(upper=170, lower=150, boundary=125),
                    mem=dict(upper=8000, lower=6000, boundary=2048),
                    disk=dict(upper=100, lower=20, boundary=10),
                    net=dict(upper=100, lower=20, boundary=10),
                    energy=dict(upper=15, lower=5, boundary=3)
                )
            )
            handler.add_limit(container)

        application = dict(
            type='limit',
            name='app1',
            resources=dict(
                cpu=dict(upper=200, lower=150, boundary=50),
                mem=dict(upper=14000, lower=2000, boundary=4000),
                disk=dict(upper=100, lower=10, boundary=20),
                net=dict(upper=100, lower=10, boundary=20),
                energy=dict(upper=50, lower=5, boundary=5)
            )
        )
        handler.add_limit(application)

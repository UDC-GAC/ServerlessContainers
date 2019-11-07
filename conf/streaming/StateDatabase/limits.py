# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["master0", "master1",
              "kafka0", "kafka1", "kafka2", "kafka3",
              "hibench0", "hibench1",
              "slave0", "slave1", "slave2", "slave3", "slave4", "slave5", "slave6", "slave7", "slave8", "slave9"]
applications = ["spark_user0", "hibenches_user0", "kafkas_user0", "spark_user1", "hibenches_user1", "kafkas_user1"]

base_limits = dict(
    type='limit',
    name="base_container",
    resources=dict(
        cpu=dict(upper=170, lower=150, boundary=25),
        mem=dict(upper=8000, lower=6000, boundary=2048),
        disk=dict(upper=100, lower=20, boundary=10),
        net=dict(upper=100, lower=20, boundary=10),
        energy=dict(upper=15, lower=5, boundary=3)
    )
)

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
                    cpu=dict(upper=170, lower=150, boundary=25),
                    mem=dict(upper=8000, lower=6000, boundary=2048),
                    disk=dict(upper=100, lower=20, boundary=10),
                    net=dict(upper=100, lower=20, boundary=10),
                    energy=dict(upper=15, lower=5, boundary=3)
                )
            )
            handler.add_limit(container)

        for a in applications:
            application = dict(
                type='limit',
                name=a,
                resources=dict(
                    cpu=dict(upper=200, lower=150, boundary=50),
                    mem=dict(upper=4000, lower=2000, boundary=1000),
                    energy=dict(upper=50, lower=5, boundary=5)
                )
            )
            handler.add_limit(application)

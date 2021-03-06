# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["master0", "master1",
              "aux0", "aux1",
              "pre0", "pre1", "pre2", "pre3",
              "comp0", "comp1", "comp2", "comp3", "comp4", "comp5"]
applications = ["aux_user0","pre_user0","comp_user0"]

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

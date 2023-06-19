# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


guardian = dict(
    name="guardian",
    type="service",
    heartbeat="",
    config=dict(
        ACTIVE=False,
        DEBUG=True,
        EVENT_TIMEOUT=120,
        WINDOW_DELAY=12,
        WINDOW_TIMELAPSE=10
    )
)

scaler = dict(
    name="scaler",
    type="service",
    heartbeat="",
    config=dict(
        ACTIVE=False,
        DEBUG=True,
        REQUEST_TIMEOUT=60,
        POLLING_FREQUENCY=5
    )
)

database_snapshoter = dict(
    name="database_snapshoter",
    type="service",
    heartbeat="",
    config=dict(
        ACTIVE=False,
        DEBUG=True
    )
)

structures_snapshoter = dict(
    name="structures_snapshoter",
    type="service",
    heartbeat="",
    config=dict(
        ACTIVE=False,
        DEBUG=True
    )
)

refeeder = dict(
    name="refeeder",
    type="service",
    heartbeat="",
    config=dict(
        ACTIVE=False,
        DEBUG=True
    )
)

sanity_checker = dict(
    name="sanity_checker",
    type="service",
    heartbeat="",
    config=dict(
        DELAY=30,
        DEBUG=True
    )
)

rebalancer  = dict(
    name="rebalancer",
    type="service",
    heartbeat="",
    config=dict(
        DEBUG=True
    )
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "services"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists("services"):
        print("Adding 'services' document")
        handler.add_service(scaler)
        handler.add_service(guardian)
        handler.add_service(database_snapshoter)
        handler.add_service(structures_snapshoter)
        handler.add_service(refeeder)
        handler.add_service(sanity_checker)
        handler.add_service(rebalancer)

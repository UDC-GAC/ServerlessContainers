# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

watt_wizard = dict(
    name="watt_wizard",
    type="service",
    heartbeat="",
    config=dict(
        DEBUG=True
    )
)

watt_trainer = dict(
    name="watt_trainer",
    type="service",
    heartbeat="",
    config=dict(
        DEBUG=True
    )
)

energy_manager = dict(
    name="energy_manager",
    type="service",
    heartbeat="",
    config=dict(
        POLLING_FREQUENCY=10,
        DEBUG=True
    )
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()

    if handler.database_exists("services"):
        print("Adding 'energy services' document")
        handler.add_service(energy_manager)
        #handler.add_service(watt_wizard)
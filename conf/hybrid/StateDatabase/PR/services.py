# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


guardian = dict(
    name="guardian",
    type="service",
    heartbeat="",
    config=dict(
        STRUCTURE_GUARDED="container",
        WINDOW_TIMELAPSE=10,
        WINDOW_DELAY=10,
        EVENT_TIMEOUT=130,
        DEBUG=True
    )
)


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "services"

    if handler.database_exists("services"):
        print("Adding 'guardian service' document")
        try:
            service = handler.get_service("guardian")
            service["config"] = guardian["config"]
            handler.update_service(service)
        except ValueError:
            handler.add_service(guardian)


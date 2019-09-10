# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

from conf.scal_32_ST.StateDatabase.structures.single_app import add_single_application
from conf.scal_32_ST.StateDatabase.structures.multiple_app import add_multiple_application
from conf.scal_32_ST.StateDatabase.structures.containers import add_containers
from conf.scal_32_ST.StateDatabase.structures.hosts import add_hosts

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "structures"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)
    add_hosts(handler)
    #add_single_application(handler)
    add_multiple_application(handler)
    add_containers(handler)

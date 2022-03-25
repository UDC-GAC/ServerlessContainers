from flask import g
import os

import src.StateDatabase.couchdb as couchDB

MAX_TRIES = 10
BACK_OFF_TIME = 2
COUCHDB_URL = os.getenv('COUCHDB_URL')
if not COUCHDB_URL:
    COUCHDB_URL = "couchdb"


def get_db():
    global COUCHDB_URL
    """Opens a new database connection if there is none yet for the current application context."""
    if not hasattr(g, 'db_handler'):
        g.db_handler = couchDB.CouchDBServer(couchdb_url=COUCHDB_URL)
    return g.db_handler

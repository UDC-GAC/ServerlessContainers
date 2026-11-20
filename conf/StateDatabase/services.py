# /usr/bin/python
"""Initialize the 'services' database from a YAML configuration file.

By default, the configuration file is 'services.yml', located in the same directory as this script, but another one
can be passed as the first argument:

    python3 conf/StateDatabase/services.py [path/to/services.yml]

See 'services.yml' for a description of the configuration format.
"""
import os
import sys

import yaml

import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services.yml")


def build_services(config):
    services = []
    for name, service_config in (config.get("services") or {}).items():
        if not isinstance(service_config or {}, dict):
            raise ValueError("Configuration of service '{0}' must be a mapping, got: {1}".format(name, service_config))
        services.append(dict(name=name, type="service", heartbeat="", config=service_config or {}))
    return services


def load_config(config_file):
    with open(config_file, "r") as f:
        return yaml.safe_load(f) or {}


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    # Build the services before touching the database, so an invalid configuration does not leave it empty
    services = build_services(load_config(config_file))

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "services"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists(database):
        print("Adding 'services' documents from {0}".format(config_file))
        for service in services:
            handler.add_service(service)
